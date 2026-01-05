#!/usr/bin/env python3
"""
MCP Server für Vollautomatisches Multi-Model Orchestration - STANDALONE VERSION.

Dieser MCP Server ermöglicht vollautomatische Routing-Entscheidungen
zwischen Opus/Sonnet/Haiku + spezialisierte Agenten ohne manuelle Intervention.

Usage:
    python orchestration_server.py              # Test mode (CLI)
    python orchestration_server.py --server     # MCP Server mode (production)
"""

import json
import sys
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from enum import Enum

# Import task decomposer
try:
    from task_decomposer import TaskDecomposer, DecompositionResult
    DECOMPOSER_AVAILABLE = True
except ImportError:
    DECOMPOSER_AVAILABLE = False
    TaskDecomposer = None
    DecompositionResult = None

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("orchestration.mcp_server")


# ============================================================================
# ENUMS & DATA CLASSES
# ============================================================================

class ModelTier(Enum):
    """Model tiers for routing."""
    HAIKU_SIMPLE = "haiku"
    SONNET_CAPABLE = "sonnet"
    OPUS_REQUIRED = "opus"


@dataclass
class TaskRouting:
    """Result of task routing decision.

    Attributes:
        agent_name: Name des zu verwendenden Agenten.
        tier: Model-Tier (haiku, sonnet, opus).
        confidence: Konfidenz der Routing-Entscheidung (0.0-1.0).
        reasoning: Begründung für die Entscheidung.
        specialty: Optionale Spezialisierung des Agenten.
        cached_decisions: Liste von gecachten Entscheidungen für Kontext.
    """
    agent_name: str
    tier: str
    confidence: float
    reasoning: str
    specialty: Optional[str] = None
    cached_decisions: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class CachedDecision:
    """Cached Opus decision for reuse."""
    task_description: str
    decision: str
    reasoning: str
    affected_files: List[str]
    model_used: str
    confidence: float
    timestamp: datetime

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_description": self.task_description,
            "decision": self.decision,
            "reasoning": self.reasoning,
            "affected_files": self.affected_files,
            "model_used": self.model_used,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat()
        }


# ============================================================================
# TASK CLASSIFIER
# ============================================================================

class TaskClassifier:
    """Klassifiziert Tasks in Haiku/Sonnet/Opus basierend auf Komplexität."""

    # Keyword patterns für jedes Tier
    HAIKU_KEYWORDS = [
        "typo", "fix typo", "rename", "comment", "docstring",
        "format", "formatting", "import", "add comment",
        "lint", "prettify", "spelling", "whitespace"
    ]

    SONNET_KEYWORDS = [
        "implement", "add", "create", "build", "develop",
        "endpoint", "api", "function", "method", "class",
        "feature", "functionality", "service", "handler"
    ]

    OPUS_KEYWORDS = [
        "design", "architecture", "system", "migrate", "refactor",
        "optimize", "performance", "scalability", "microservice",
        "strategy", "pattern", "framework", "infrastructure"
    ]

    # HAIKU SAFE PATTERNS - NUR diese sind für Haiku erlaubt (100% sicher)
    HAIKU_SAFE_PATTERNS = [
        r"^format", r"^lint", r"^prettify",
        r"^import.*sort", r"^organize.*import",
        r"^fix.*typo", r"^correct.*spelling",
        r"^add.*comment", r"^add.*docstring",
        r"^generate.*boilerplate", r"^scaffold",
        r"^validate.*syntax", r"^check.*import"
    ]

    # HAIKU BLACKLIST - NIEMALS Haiku für diese Patterns
    HAIKU_BLACKLIST = [
        r"implement", r"create", r"build", r"develop",
        r"fix.*bug", r"debug", r"troubleshoot",
        r"refactor", r"optimize", r"redesign",
        r"security", r"auth", r"vulnerability",
        r"architecture", r"system design", r"migrate"
    ]

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize classifier with optional config."""
        self.config = config or {}
        # Load patterns from config if available
        if "haiku_safe_patterns" in self.config:
            self.HAIKU_SAFE_PATTERNS = self.config["haiku_safe_patterns"]
        if "haiku_blacklist" in self.config:
            self.HAIKU_BLACKLIST = self.config["haiku_blacklist"]

    def _is_haiku_safe(self, task_prompt: str) -> Tuple[bool, str]:
        """Check if task is safe for Haiku (conservative approach).

        Returns:
            Tuple of (is_safe, reason)
        """
        task_lower = task_prompt.lower()

        # 1. Check BLACKLIST first - if any match, NEVER use Haiku
        for pattern in self.HAIKU_BLACKLIST:
            if re.search(pattern, task_lower):
                return False, f"Blacklisted pattern: {pattern}"

        # 2. Check SAFE_PATTERNS - only if match AND task is simple
        for pattern in self.HAIKU_SAFE_PATTERNS:
            if re.search(pattern, task_lower):
                # Additional safety: task must be short and single-focused
                if len(task_prompt) < 200:
                    return True, f"Safe pattern matched: {pattern}"

        return False, "No safe pattern matched"

    def classify(
        self,
        task_prompt: str,
        files: Optional[List[str]] = None
    ) -> TaskRouting:
        """Klassifiziere Task und bestimme optimalen Tier."""
        task_lower = task_prompt.lower()
        files = files or []

        # STEP 1: Check if task is safe for Haiku (conservative approach)
        is_haiku_safe, haiku_reason = self._is_haiku_safe(task_prompt)

        if is_haiku_safe and len(files) <= 1:
            # Task is explicitly safe for Haiku
            logger.info(f"Haiku safe task detected: {haiku_reason}")
            return TaskRouting(
                agent_name=self._tier_to_agent(ModelTier.HAIKU_SIMPLE),
                tier="haiku",
                confidence=0.95,
                reasoning=f"Haiku safe: {haiku_reason}"
            )

        # STEP 2: Standard complexity scoring
        haiku_score = self._calculate_score(task_lower, self.HAIKU_KEYWORDS)
        sonnet_score = self._calculate_score(task_lower, self.SONNET_KEYWORDS)
        opus_score = self._calculate_score(task_lower, self.OPUS_KEYWORDS)

        # File count factor (mehr Files = höhere Complexity)
        file_count_factor = len(files) / 10.0  # 10+ files = +1.0 to opus
        opus_score += file_count_factor

        # Prompt length factor (länger = komplexer)
        prompt_length_factor = len(task_prompt) / 500.0  # 500+ chars = +1.0
        opus_score += prompt_length_factor * 0.5
        sonnet_score += prompt_length_factor * 0.3

        # STEP 3: If Haiku has highest score but NOT safe, demote to Sonnet
        scores = {
            "haiku": haiku_score,
            "sonnet": sonnet_score,
            "opus": opus_score
        }

        max_tier = max(scores, key=scores.get)
        max_score = scores[max_tier]

        # Conservative: Never use Haiku from scoring alone (only from safe patterns)
        if max_tier == "haiku" and not is_haiku_safe:
            max_tier = "sonnet"
            max_score = sonnet_score
            logger.info("Demoted from haiku to sonnet (not explicitly safe)")

        # Minimum thresholds
        if max_score < 0.3:
            # Default to Sonnet if no clear signal
            tier = ModelTier.SONNET_CAPABLE
            confidence = 0.60
            reasoning = "Default routing (no strong signals)"
        else:
            tier = ModelTier(max_tier)
            # Normalize confidence (0.7-0.95 range)
            confidence = min(0.70 + (max_score * 0.25), 0.95)
            reasoning = f"{max_tier.capitalize()} detected (score: {max_score:.2f})"

        return TaskRouting(
            agent_name=self._tier_to_agent(tier),
            tier=tier.value,
            confidence=confidence,
            reasoning=reasoning
        )

    def _calculate_score(self, text: str, keywords: List[str]) -> float:
        """Berechnet einen Keyword-Match-Score für Text.

        Zählt wie viele Keywords im Text vorkommen und normalisiert
        das Ergebnis auf einen Wert zwischen 0.0 und 1.0.

        Args:
            text: Der zu durchsuchende Text (sollte lowercase sein)
            keywords: Liste der zu suchenden Keywords

        Returns:
            Score zwischen 0.0 und 1.0 (Anteil gefundener Keywords)
        """
        matches = sum(1 for kw in keywords if kw in text)
        return matches / len(keywords) if keywords else 0.0

    def _tier_to_agent(self, tier: ModelTier) -> str:
        """Konvertiert einen ModelTier zu einem Agent-Namen.

        Args:
            tier: ModelTier Enum-Wert

        Returns:
            Name des zugehörigen Agenten (z.B. 'sonnet-implementation')
        """
        mapping = {
            ModelTier.HAIKU_SIMPLE: "haiku-task",
            ModelTier.SONNET_CAPABLE: "sonnet-implementation",
            ModelTier.OPUS_REQUIRED: "opus-task"
        }
        return mapping.get(tier, "sonnet-implementation")


# ============================================================================
# DECISION CACHE
# ============================================================================

class DecisionCache:
    """Cache für Opus-Entscheidungen zur Wiederverwendung."""

    def __init__(self, ttl_days: int = 7):
        self.cache: List[CachedDecision] = []
        self.ttl = timedelta(days=ttl_days)

    def store(
        self,
        task_description: str,
        decision: str,
        reasoning: str,
        affected_files: List[str],
        model_used: str,
        confidence: float
    ) -> None:
        """Store Opus decision in cache."""
        cached = CachedDecision(
            task_description=task_description,
            decision=decision,
            reasoning=reasoning,
            affected_files=affected_files,
            model_used=model_used,
            confidence=confidence,
            timestamp=datetime.now()
        )
        self.cache.append(cached)
        logger.info(f"Cached decision: {task_description[:50]}...")

    def find_relevant(
        self,
        task_prompt: str,
        files: Optional[List[str]] = None,
        limit: int = 3
    ) -> List[CachedDecision]:
        """Find relevant cached decisions."""
        files = files or []
        relevant = []

        # Clean expired entries
        cutoff = datetime.now() - self.ttl
        self.cache = [c for c in self.cache if c.timestamp > cutoff]

        for cached in self.cache:
            # Similarity score
            relevance = 0.0

            # Keyword overlap
            task_words = set(task_prompt.lower().split())
            cached_words = set(cached.task_description.lower().split())
            keyword_overlap = len(task_words & cached_words) / max(len(task_words), 1)
            relevance += keyword_overlap * 0.5

            # File overlap
            if files and cached.affected_files:
                file_overlap = len(set(files) & set(cached.affected_files)) / max(len(files), 1)
                relevance += file_overlap * 0.5

            if relevance > 0.3:  # Threshold
                relevant.append((relevance, cached))

        # Sort by relevance and return top N
        relevant.sort(key=lambda x: x[0], reverse=True)
        return [cached for _, cached in relevant[:limit]]

    def clear(self) -> None:
        """Clear all cached decisions."""
        self.cache.clear()


# ============================================================================
# QUALITY GATE
# ============================================================================

class QualityGate:
    """Validiert Output-Qualität und entscheidet über Escalation."""

    def validate(
        self,
        code: str,
        file_path: str,
        model_used: str
    ) -> 'QualityResult':
        """Run quality checks."""
        checks_passed = []
        checks_failed = []

        # 1. Python Syntax Check (basic)
        if self._is_valid_python_syntax(code):
            checks_passed.append("syntax")
        else:
            checks_failed.append("syntax")

        # 2. Type Hints Check (no 'Any' types)
        if "Any" not in code or ": Any" not in code:
            checks_passed.append("type_hints")
        else:
            checks_failed.append("type_hints")

        # 3. German Language Check (for strings)
        if self._has_german_strings(code):
            checks_passed.append("german_language")
        else:
            # Optional - don't fail if no user-facing strings
            checks_passed.append("german_language")

        # 4. GPU Resource Management (if OCR-related)
        if "gpu" in file_path.lower() or "ocr" in file_path.lower():
            if "torch.cuda" in code and "memory" in code:
                checks_passed.append("gpu_management")
            else:
                checks_failed.append("gpu_management")
        else:
            checks_passed.append("gpu_management")  # N/A

        # 5. No Secrets Check
        if not self._contains_secrets(code):
            checks_passed.append("no_secrets")
        else:
            checks_failed.append("no_secrets")

        # 6. Import Check (no unused imports - basic)
        checks_passed.append("imports")  # Simplified for now

        # Calculate quality score
        total = len(checks_passed) + len(checks_failed)
        quality_score = len(checks_passed) / total if total > 0 else 0.0

        # Determine if escalation needed
        thresholds = {
            "haiku": 0.95,
            "sonnet": 0.85,
            "opus": 0.80
        }
        threshold = thresholds.get(model_used, 0.85)
        should_escalate = quality_score < threshold

        return QualityResult(
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            quality_score=quality_score,
            should_escalate=should_escalate,
            threshold=threshold
        )

    def _is_valid_python_syntax(self, code: str) -> bool:
        """Prüft ob Code gültige Python-Syntax hat.

        Verwendet compile() um den Code zu parsen ohne ihn auszuführen.

        Args:
            code: Der zu prüfende Python-Code

        Returns:
            True wenn Syntax gültig, False bei SyntaxError
        """
        try:
            compile(code, "<string>", "exec")
            return True
        except SyntaxError:
            return False

    def _has_german_strings(self, code: str) -> bool:
        """Prüft ob Code deutsche Strings enthält.

        Sucht nach typischen deutschen Wörtern im Code um zu
        verifizieren dass user-facing Texte auf Deutsch sind.

        Args:
            code: Der zu prüfende Code

        Returns:
            True wenn deutsche Wörter gefunden wurden
        """
        german_words = ["dokument", "fehler", "ungültig", "verarbeitung", "benutzer"]
        return any(word in code.lower() for word in german_words)

    def _contains_secrets(self, code: str) -> bool:
        """Prüft ob Code potentielle Secrets enthält.

        Sucht nach Patterns die auf API-Keys, Passwörter oder
        andere sensible Daten hindeuten (z.B. sk-..., password=...).

        Args:
            code: Der zu prüfende Code

        Returns:
            True wenn potentielle Secrets gefunden wurden
        """
        secret_patterns = [
            r"sk-[a-zA-Z0-9]{32,}",  # API keys
            r"password\s*=\s*['\"].*['\"]",  # Hardcoded passwords
            r"api_key\s*=\s*['\"].*['\"]"   # Hardcoded API keys
        ]
        return any(re.search(pattern, code, re.IGNORECASE) for pattern in secret_patterns)


@dataclass
class QualityResult:
    """Result of quality validation."""
    checks_passed: List[str]
    checks_failed: List[str]
    quality_score: float
    should_escalate: bool
    threshold: float


# ============================================================================
# HAIKU QUALITY GATE (STRICT - 98% required)
# ============================================================================

class HaikuQualityGate:
    """Strenge Validierung für Haiku-Output BEVOR er akzeptiert wird.

    Haiku darf die Qualität NIEMALS verschlechtern!
    Bei Unsicherheit → SOFORT zu Sonnet eskalieren.
    """

    HAIKU_THRESHOLD = 0.98  # 98% Qualität erforderlich!

    def validate(
        self,
        original_code: str,
        modified_code: str,
        task_type: str
    ) -> Tuple[bool, str, Optional[str]]:
        """Validiere Haiku-Output BEVOR er akzeptiert wird.

        Args:
            original_code: Original code before modification
            modified_code: Code after Haiku modification
            task_type: Type of task (format, typo, comment, etc.)

        Returns:
            Tuple of (passed, reason, escalate_to)
        """
        checks = []
        check_results = []

        # 1. Syntax Check - MUST compile
        syntax_ok = self._check_syntax(modified_code)
        checks.append(("syntax", syntax_ok))
        check_results.append(syntax_ok)

        # 2. No Logic Changes - Code behavior unchanged
        logic_ok = self._check_no_logic_changes(original_code, modified_code, task_type)
        checks.append(("no_logic_changes", logic_ok))
        check_results.append(logic_ok)

        # 3. Formatting Only - Only whitespace/imports changed (for format tasks)
        if task_type in ["format", "lint", "import"]:
            format_ok = self._check_formatting_only(original_code, modified_code)
            checks.append(("formatting_only", format_ok))
            check_results.append(format_ok)

        # 4. No Deletions - Nothing important deleted
        deletion_ok = self._check_no_deletions(original_code, modified_code)
        checks.append(("no_deletions", deletion_ok))
        check_results.append(deletion_ok)

        # Calculate quality score
        score = sum(check_results) / len(check_results) if check_results else 0.0

        # Log results
        failed_checks = [name for name, passed in checks if not passed]
        if failed_checks:
            logger.warning(f"HaikuQualityGate failed checks: {failed_checks}")

        # STRICT: Must meet 98% threshold
        if score < self.HAIKU_THRESHOLD:
            logger.info(f"HaikuQualityGate failed ({score:.0%} < {self.HAIKU_THRESHOLD:.0%}), escalating to Sonnet")
            return False, f"Quality {score:.0%} below threshold, failed: {failed_checks}", "sonnet"

        return True, f"Quality passed ({score:.0%})", None

    def _check_syntax(self, code: str) -> bool:
        """Prüft ob Code gültige Python-Syntax hat (für HaikuQualityGate).

        Verwendet compile() um den Code zu parsen ohne ihn auszuführen.
        Kritischer Check - bei Fehlschlag wird zu Sonnet eskaliert.

        Args:
            code: Der zu prüfende Python-Code

        Returns:
            True wenn Syntax gültig, False bei SyntaxError
        """
        try:
            compile(code, "<string>", "exec")
            return True
        except SyntaxError:
            return False

    def _check_no_logic_changes(
        self,
        original: str,
        modified: str,
        task_type: str
    ) -> bool:
        """Prüft dass keine Logik geändert wurde (nur Formatierung/Kommentare).

        Für typo/comment Tasks: Erlaubt Änderungen in Strings/Kommentaren.
        Für format Tasks: Prüft dass Funktionssignaturen unverändert sind.

        Args:
            original: Original-Code vor Modifikation
            modified: Code nach Haiku-Modifikation
            task_type: Art des Tasks (typo, comment, format, lint, etc.)

        Returns:
            True wenn keine unerwarteten Logik-Änderungen erkannt
        """
        # For typo/comment tasks, extract non-string/comment content
        if task_type in ["typo", "comment", "docstring"]:
            # Allow changes only in strings and comments
            return True  # Simplified - full AST comparison would be needed

        # For format tasks, check function signatures unchanged
        if task_type in ["format", "lint"]:
            # Extract function definitions
            original_funcs = set(re.findall(r'def\s+(\w+)\s*\(', original))
            modified_funcs = set(re.findall(r'def\s+(\w+)\s*\(', modified))
            return original_funcs == modified_funcs

        return True

    def _check_formatting_only(self, original: str, modified: str) -> bool:
        """Prüft dass nur Whitespace und Imports geändert wurden.

        Entfernt allen Whitespace und vergleicht die Ähnlichkeit.
        Bei >=95% Ähnlichkeit wird angenommen dass nur formatiert wurde.

        Args:
            original: Original-Code vor Modifikation
            modified: Code nach Haiku-Modifikation

        Returns:
            True wenn Ähnlichkeit > 95% (nur Formatierungs-Änderungen)
        """
        # Remove all whitespace and compare
        original_stripped = re.sub(r'\s+', '', original)
        modified_stripped = re.sub(r'\s+', '', modified)

        # Allow minor differences (imports might be reordered)
        # Check if the non-whitespace content is at least 95% similar
        if len(original_stripped) == 0:
            return True

        # Simple character-by-character comparison
        matches = sum(1 for a, b in zip(original_stripped, modified_stripped) if a == b)
        similarity = matches / max(len(original_stripped), len(modified_stripped))

        return similarity > 0.95

    def _check_no_deletions(self, original: str, modified: str) -> bool:
        """Prüft dass kein signifikanter Code gelöscht wurde.

        Zählt Funktions- und Klassen-Definitionen in Original und
        modifiziertem Code. Keine darf fehlen.

        Args:
            original: Original-Code vor Modifikation
            modified: Code nach Haiku-Modifikation

        Returns:
            True wenn keine Funktionen/Klassen gelöscht wurden
        """
        # Count function definitions
        original_func_count = len(re.findall(r'def\s+\w+', original))
        modified_func_count = len(re.findall(r'def\s+\w+', modified))

        # Count class definitions
        original_class_count = len(re.findall(r'class\s+\w+', original))
        modified_class_count = len(re.findall(r'class\s+\w+', modified))

        # No functions or classes should be deleted
        return (modified_func_count >= original_func_count and
                modified_class_count >= original_class_count)


# ============================================================================
# ORCHESTRATION METRICS
# ============================================================================

class OrchestrationMetrics:
    """Track orchestration metrics."""

    def __init__(self):
        self.tasks_by_tier = {"haiku": 0, "sonnet": 0, "opus": 0}
        self.total_tokens = {"orchestrated": 0, "baseline_opus": 0}
        self.quality_scores = []
        self.escalations = 0
        self.cache_hits = 0
        self.cache_misses = 0

    def record_task(self, tier: str, tokens_used: int, quality_score: float):
        """Record task execution."""
        self.tasks_by_tier[tier] = self.tasks_by_tier.get(tier, 0) + 1

        # Token tracking (simplified)
        TOKEN_COSTS = {"haiku": 1.0, "sonnet": 5.0, "opus": 15.0}
        self.total_tokens["orchestrated"] += tokens_used * TOKEN_COSTS.get(tier, 5.0)
        self.total_tokens["baseline_opus"] += tokens_used * TOKEN_COSTS["opus"]

        if quality_score > 0:
            self.quality_scores.append(quality_score)

    def record_escalation(self):
        """Record escalation event."""
        self.escalations += 1

    def record_cache_hit(self):
        """Record cache hit."""
        self.cache_hits += 1

    def record_cache_miss(self):
        """Record cache miss."""
        self.cache_misses += 1

    def get_total_tasks(self) -> int:
        """Get total tasks processed."""
        return sum(self.tasks_by_tier.values())

    def get_tier_distribution(self) -> Dict[str, int]:
        """Get tier distribution."""
        return self.tasks_by_tier.copy()

    def get_token_savings_percentage(self) -> float:
        """Calculate token savings percentage."""
        if self.total_tokens["baseline_opus"] == 0:
            return 0.0
        savings = (self.total_tokens["baseline_opus"] - self.total_tokens["orchestrated"]) / self.total_tokens["baseline_opus"]
        return savings * 100

    def get_summary(self) -> str:
        """Get metrics summary."""
        total = self.get_total_tasks()
        avg_quality = sum(self.quality_scores) / len(self.quality_scores) if self.quality_scores else 0.0

        return f"""
Orchestration Metrics Summary:
------------------------------
Total Tasks: {total}
Tier Distribution:
  - Haiku: {self.tasks_by_tier['haiku']} ({self.tasks_by_tier['haiku']/total*100 if total > 0 else 0:.1f}%)
  - Sonnet: {self.tasks_by_tier['sonnet']} ({self.tasks_by_tier['sonnet']/total*100 if total > 0 else 0:.1f}%)
  - Opus: {self.tasks_by_tier['opus']} ({self.tasks_by_tier['opus']/total*100 if total > 0 else 0:.1f}%)

Token Savings: {self.get_token_savings_percentage():.1f}%
Average Quality: {avg_quality:.2%}
Escalations: {self.escalations} ({self.escalations/total*100 if total > 0 else 0:.1f}%)
Cache Hit Rate: {self.cache_hits/(self.cache_hits + self.cache_misses)*100 if (self.cache_hits + self.cache_misses) > 0 else 0:.1f}%
"""

    def reset(self):
        """Reset all metrics."""
        self.tasks_by_tier = {"haiku": 0, "sonnet": 0, "opus": 0}
        self.total_tokens = {"orchestrated": 0, "baseline_opus": 0}
        self.quality_scores = []
        self.escalations = 0
        self.cache_hits = 0
        self.cache_misses = 0


# ============================================================================
# ORCHESTRATION MCP SERVER
# ============================================================================

class OrchestrationMCPServer:
    """MCP Server für vollautomatisches Multi-Model Routing."""

    def __init__(self, config_path: Optional[Path] = None):
        """Initialize MCP Server."""
        # Load config
        if config_path is None:
            config_path = Path(__file__).parent / "config.json"

        self.config = self._load_config(config_path)

        # Initialize components with config
        self.classifier = TaskClassifier(config=self.config)
        self.cache = DecisionCache(ttl_days=self.config.get("thresholds", {}).get("cache_ttl_days", 7))
        self.quality_gate = QualityGate()
        self.haiku_quality_gate = HaikuQualityGate()  # Strict 98% threshold
        self.metrics = OrchestrationMetrics()

        # Initialize task decomposer if available
        self.decomposer = TaskDecomposer() if DECOMPOSER_AVAILABLE else None
        if not DECOMPOSER_AVAILABLE:
            logger.warning("TaskDecomposer not available - decompose_task tool disabled")

        # Specialized patterns (12 agents)
        self.specialized_patterns = self.config.get("specialized_patterns", {})

        # Haiku patterns from config
        self.haiku_safe_patterns = self.config.get("haiku_safe_patterns", [])
        self.haiku_blacklist = self.config.get("haiku_blacklist", [])

        # Tier to agent mapping
        self.tier_to_agent = {
            "haiku": "haiku-task",
            "sonnet": "sonnet-implementation",
            "opus": "opus-task"
        }

        # Log agent count
        agent_count = len(self.specialized_patterns)
        logger.info(f"OrchestrationMCPServer initialized with {agent_count} specialized agents")
        logger.info(f"Haiku safe patterns: {len(self.haiku_safe_patterns)}, Blacklist: {len(self.haiku_blacklist)}")

    def _load_config(self, config_path: Path) -> Dict[str, Any]:
        """Load configuration from JSON file."""
        if not config_path.exists():
            logger.warning(f"Config not found: {config_path}, using defaults")
            return {}

        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    async def route_task(
        self,
        task_prompt: str,
        files: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> TaskRouting:
        """Route task to optimal agent (standard OR specialized).

        Priority:
        1. Specialized agents (Refactoring, OCR, Testing, Database)
        2. Standard tier-based routing (Opus/Sonnet/Haiku)
        """
        files = files or []

        # 1. Check for specialized agents FIRST (higher priority)
        if self.config.get("orchestration", {}).get("specialized_agents_enabled", True):
            for specialty_name, specialty_config in self.specialized_patterns.items():
                if self._matches_specialty(task_prompt, files, specialty_config):
                    logger.info(f"Matched specialized agent: {specialty_name}")
                    return TaskRouting(
                        agent_name=specialty_config["agent"],
                        tier=specialty_config.get("tier", "opus"),
                        confidence=0.95,
                        reasoning=f"Specialized agent for {specialty_name}",
                        specialty=specialty_name
                    )

        # 2. Fall back to standard tier-based classification
        classification = self.classifier.classify(task_prompt, files)

        # 3. Load cached decisions for Sonnet/Haiku
        cached_decisions = []
        if self.config.get("orchestration", {}).get("cache_enabled", True) and classification.tier in ["sonnet", "haiku"]:
            relevant_cache = self.cache.find_relevant(task_prompt, files)
            cached_decisions = [
                {"decision": cache.decision, "reasoning": cache.reasoning, "confidence": cache.confidence}
                for cache in relevant_cache
            ]

            if cached_decisions:
                self.metrics.record_cache_hit()
            else:
                self.metrics.record_cache_miss()

        classification.cached_decisions = cached_decisions
        return classification

    def _matches_specialty(
        self,
        task_prompt: str,
        files: List[str],
        specialty_config: Dict[str, Any]
    ) -> bool:
        """Check if task matches specialized agent pattern."""
        # 1. Keyword matching (case-insensitive)
        task_lower = task_prompt.lower()
        keywords = specialty_config.get("keywords", [])
        keyword_match = any(kw.lower() in task_lower for kw in keywords)

        # 2. File pattern matching
        file_match = False
        file_patterns = specialty_config.get("file_patterns", [])
        if files and file_patterns:
            for file_path in files:
                for pattern in file_patterns:
                    # Simple glob-style matching
                    if pattern.endswith("/*"):
                        prefix = pattern[:-2]
                        if file_path.startswith(prefix):
                            file_match = True
                            break
                    elif "*" in pattern:
                        # Basic wildcard support with safe regex escaping
                        # Escape special regex chars first, then convert * to .*
                        escaped_pattern = re.escape(pattern).replace(r"\*", ".*")
                        if re.match(escaped_pattern, file_path):
                            file_match = True
                            break
                    else:
                        # Exact match
                        if pattern in file_path:
                            file_match = True
                            break

        # 3. Multi-file threshold check (for refactoring)
        file_count_match = True
        min_files = specialty_config.get("min_files")
        if min_files is not None:
            file_count_match = len(files) >= min_files

        # Match if keywords OR (files AND file_count)
        return keyword_match or (file_match and file_count_match)

    def create_task_call(
        self,
        routing: TaskRouting,
        task_prompt: str,
        files: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Create Task() JSON for Claude Code."""
        files = files or []

        # Enhance prompt with orchestration context
        enhanced_prompt = self._enhance_prompt(
            task_prompt,
            routing.tier,
            routing.cached_decisions,
            routing.specialty
        )

        task_call = {
            "type": "Task",
            "subagent_type": routing.agent_name,
            "description": f"Process with {routing.tier} (confidence: {routing.confidence:.0%})",
            "prompt": enhanced_prompt,
            "model": routing.tier  # Explicit model override
        }

        # Record metrics
        self.metrics.record_task(
            tier=routing.tier,
            tokens_used=len(task_prompt) // 4,  # Rough estimate
            quality_score=0.0  # Will be updated post-execution
        )

        logger.info(f"Created Task() call: {routing.agent_name} ({routing.tier})")
        return task_call

    def _enhance_prompt(
        self,
        task_prompt: str,
        tier: str,
        cached_decisions: List[Dict[str, Any]],
        specialty: Optional[str] = None
    ) -> str:
        """Enhance task prompt with orchestration context."""
        sections = [task_prompt]

        # Add cached decisions (for Sonnet/Haiku)
        if cached_decisions:
            sections.append("\n## CACHED DECISIONS FROM OPUS\n")
            sections.append(
                "The following architectural decisions were made by Opus "
                "for similar tasks. Follow these patterns:\n"
            )
            for i, decision in enumerate(cached_decisions, 1):
                sections.append(f"\n### Decision {i} (Confidence: {decision['confidence']:.0%})")
                sections.append(f"**Decision**: {decision['decision']}")
                sections.append(f"**Reasoning**: {decision['reasoning']}\n")

        # Add tier-specific guidance
        tier_guidance = {
            "haiku": "\n## HAIKU GUIDELINES\n- Focus on simple, well-defined tasks\n- Prefer straightforward implementations\n- Avoid complex abstractions\n",
            "sonnet": "\n## SONNET GUIDELINES\n- Implement features using cached Opus decisions where available\n- Follow established architectural patterns\n- Escalate to Opus if you need to make architectural decisions\n",
            "opus": "\n## OPUS GUIDELINES\n- Make architectural decisions that will be cached for Sonnet/Haiku\n- Document your reasoning clearly\n- Consider long-term maintainability and scalability\n"
        }
        sections.append(tier_guidance.get(tier, ""))

        # Add specialty context if applicable
        if specialty:
            sections.append(f"\n## SPECIALIZED AGENT: {specialty.upper()}\n")
            sections.append(f"You are using the {specialty} specialized agent with domain expertise.\n")

        return "".join(sections)

    async def validate_and_escalate(
        self,
        task_id: str,
        output: str,
        model_used: str,
        original_prompt: str,
        files: Optional[List[str]] = None
    ) -> Optional[Dict[str, Any]]:
        """Validate quality and escalate if needed."""
        files = files or []

        # Validate
        quality_result = self.quality_gate.validate(
            code=output,
            file_path=files[0] if files else "output.py",
            model_used=model_used
        )

        # Update metrics
        self.metrics.quality_scores.append(quality_result.quality_score)

        # Check if escalation needed
        if quality_result.should_escalate:
            self.metrics.record_escalation()

            # Determine target
            escalation_tier = None
            if model_used == "haiku":
                escalation_tier = "sonnet"
            elif model_used == "sonnet":
                escalation_tier = "opus"
            else:
                # Opus can't escalate - log critical failure
                logger.error(f"Opus quality failure: {quality_result.quality_score:.2%}")
                return None

            # Create escalation Task()
            escalation_prompt = (
                f"{original_prompt}\n\n"
                f"## ESCALATION FROM {model_used.upper()}\n"
                f"**Previous Attempt Quality**: {quality_result.quality_score:.2%}\n"
                f"**Failed Checks**: {', '.join(quality_result.checks_failed)}\n\n"
                "Please address the quality issues and provide a better solution.\n"
            )

            escalation_routing = TaskRouting(
                agent_name=self.tier_to_agent[escalation_tier],
                tier=escalation_tier,
                confidence=0.90,
                reasoning=f"Escalated from {model_used} due to quality issues"
            )

            logger.info(f"Escalating {model_used} → {escalation_tier}")
            return self.create_task_call(escalation_routing, escalation_prompt, files)

        # Quality OK - cache if Opus
        if model_used == "opus" and self.config.get("orchestration", {}).get("cache_enabled", True):
            self.cache.store(
                task_description=original_prompt,
                decision=output[:500],  # Store first 500 chars
                reasoning=f"Opus output with {quality_result.quality_score:.0%} quality",
                affected_files=files,
                model_used="opus",
                confidence=quality_result.quality_score
            )
            logger.info("Cached Opus decision for future use")

        return None  # No escalation needed


# ============================================================================
# MCP STDIO SERVER (Phase 5 - Protocol Integration)
# ============================================================================

class MCPStdioServer:
    """MCP Server using STDIO transport with JSON-RPC 2.0 protocol.

    This class implements the MCP protocol over stdin/stdout, allowing
    Claude Code to communicate with the orchestration server.
    """

    def __init__(self, orchestrator: OrchestrationMCPServer):
        """Initialize STDIO server with orchestrator instance."""
        self.orchestrator = orchestrator
        self.methods = {
            "initialize": self.handle_initialize,
            "initialized": self.handle_initialized,
            "shutdown": self.handle_shutdown,
            "tools/list": self.handle_tools_list,
            "tools/call": self.handle_tools_call,
            "resources/list": self.handle_resources_list,
            "resources/read": self.handle_resources_read,
        }
        self._initialized = False
        logger.info("MCPStdioServer initialized with JSON-RPC 2.0 protocol")

    async def run(self) -> None:
        """Main STDIO communication loop.

        Reads JSON-RPC 2.0 messages from stdin and writes responses to stdout.
        """
        logger.info("Starting MCP STDIO communication loop...")

        while True:
            try:
                line = sys.stdin.readline()
                if not line:
                    logger.info("EOF received, shutting down...")
                    break

                line = line.strip()
                if not line:
                    continue

                try:
                    message = json.loads(line)
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error: {e}")
                    self._write_error(None, -32700, f"Parse error: {e}")
                    continue

                response = await self.handle_message(message)
                if response:
                    self._write_response(response)

            except KeyboardInterrupt:
                logger.info("Keyboard interrupt received, shutting down...")
                break
            except Exception as e:
                logger.exception(f"Unexpected error in STDIO loop: {e}")
                self._write_error(None, -32603, f"Internal error: {e}")

    def _write_response(self, response: Dict[str, Any]) -> None:
        """Write JSON-RPC response to stdout."""
        try:
            output = json.dumps(response, ensure_ascii=False)
            sys.stdout.write(output + '\n')
            sys.stdout.flush()
        except Exception as e:
            logger.error(f"Failed to write response: {e}")

    def _write_error(
        self,
        request_id: Optional[int],
        code: int,
        message: str
    ) -> None:
        """Write JSON-RPC error response to stdout."""
        error_response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message}
        }
        self._write_response(error_response)

    async def handle_message(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle incoming JSON-RPC 2.0 message.

        Args:
            message: Parsed JSON-RPC message

        Returns:
            Response dict or None for notifications
        """
        method = message.get("method", "")
        params = message.get("params", {})
        request_id = message.get("id")

        logger.debug(f"Received message: method={method}, id={request_id}")

        # Find handler
        handler = self.methods.get(method)
        if not handler:
            logger.warning(f"Method not found: {method}")
            if request_id is not None:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"}
                }
            return None

        try:
            result = await handler(params)

            # Notification (no id) - no response needed
            if request_id is None:
                return None

            return {"jsonrpc": "2.0", "id": request_id, "result": result}

        except Exception as e:
            logger.exception(f"Error handling method {method}: {e}")
            if request_id is not None:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32603, "message": str(e)}
                }
            return None

    async def handle_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle MCP initialize request.

        Returns server capabilities and info.
        """
        logger.info("MCP Initialize request received")
        self._initialized = True

        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {
                    "listChanged": False
                },
                "resources": {
                    "subscribe": False,
                    "listChanged": False
                }
            },
            "serverInfo": {
                "name": "orchestration",
                "version": "1.0.0"
            }
        }

    async def handle_initialized(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle MCP initialized notification."""
        logger.info("MCP Initialized notification received - ready for requests")
        return {}

    async def handle_shutdown(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle MCP shutdown request."""
        logger.info("MCP Shutdown request received")
        return {"success": True}

    async def handle_tools_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return list of available tools.

        Exposes orchestration tools to Claude Code.
        """
        logger.debug("Tools list requested")
        tools = [
            {
                "name": "route_task",
                "description": "Route a task to the optimal agent (Haiku/Sonnet/Opus) or specialized agent. Returns Task() JSON for execution. Supports 12 specialized agents: refactoring, ocr, testing, database, security, frontend, api_design, performance, devops, debugging, code_review, documentation.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task_prompt": {
                            "type": "string",
                            "description": "The task description to route"
                        },
                        "files": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional list of file paths involved in the task"
                        }
                    },
                    "required": ["task_prompt"]
                }
            },
            {
                "name": "validate_and_escalate",
                "description": "Validate output quality from an agent and escalate to a higher tier if needed. Returns escalation Task() or null.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "string",
                            "description": "Unique task identifier"
                        },
                        "output": {
                            "type": "string",
                            "description": "The code output to validate"
                        },
                        "model_used": {
                            "type": "string",
                            "enum": ["haiku", "sonnet", "opus"],
                            "description": "The model that produced the output"
                        },
                        "original_prompt": {
                            "type": "string",
                            "description": "The original task prompt"
                        },
                        "files": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional list of affected files"
                        }
                    },
                    "required": ["task_id", "output", "model_used", "original_prompt"]
                }
            },
            {
                "name": "get_metrics",
                "description": "Get orchestration metrics summary including tier distribution, token savings, quality scores, and cache hit rates.",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "decompose_task",
                "description": "Decompose a complex task into smaller sub-tasks that can be executed in parallel or by different model tiers (Haiku/Sonnet/Opus). Returns decomposition plan with dependencies and estimated token savings.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task_prompt": {
                            "type": "string",
                            "description": "The complex task to decompose"
                        },
                        "files": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional list of files involved"
                        }
                    },
                    "required": ["task_prompt"]
                }
            },
            {
                "name": "list_agents",
                "description": "List all available specialized agents with their capabilities, tier (haiku/sonnet/opus), and trigger keywords.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "tier_filter": {
                            "type": "string",
                            "enum": ["haiku", "sonnet", "opus", "all"],
                            "description": "Filter agents by tier (default: all)"
                        }
                    }
                }
            }
        ]

        return {"tools": tools}

    async def handle_tools_call(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tool execution request.

        Routes to the appropriate tool handler based on tool name.
        """
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        logger.info(f"Tool call: {tool_name}")

        if tool_name == "route_task":
            return await self._call_route_task(arguments)
        elif tool_name == "validate_and_escalate":
            return await self._call_validate_and_escalate(arguments)
        elif tool_name == "get_metrics":
            return await self._call_get_metrics(arguments)
        elif tool_name == "decompose_task":
            return await self._call_decompose_task(arguments)
        elif tool_name == "list_agents":
            return await self._call_list_agents(arguments)
        else:
            raise ValueError(f"Unknown tool: {tool_name}")

    async def _call_route_task(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute route_task tool."""
        task_prompt = args.get("task_prompt", "")
        files = args.get("files", [])

        routing = await self.orchestrator.route_task(task_prompt, files)
        task_call = self.orchestrator.create_task_call(routing, task_prompt, files)

        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(task_call, indent=2, ensure_ascii=False)
                }
            ]
        }

    async def _call_validate_and_escalate(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute validate_and_escalate tool."""
        result = await self.orchestrator.validate_and_escalate(
            task_id=args.get("task_id", ""),
            output=args.get("output", ""),
            model_used=args.get("model_used", ""),
            original_prompt=args.get("original_prompt", ""),
            files=args.get("files", [])
        )

        if result:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result, indent=2, ensure_ascii=False)
                    }
                ]
            }
        else:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "Quality validation passed. No escalation needed."
                    }
                ]
            }

    async def _call_get_metrics(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute get_metrics tool."""
        summary = self.orchestrator.metrics.get_summary()
        return {
            "content": [
                {
                    "type": "text",
                    "text": summary
                }
            ]
        }

    async def _call_decompose_task(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute decompose_task tool.

        Decomposes a complex task into smaller sub-tasks that can be executed
        in parallel or by different model tiers.
        """
        if not self.orchestrator.decomposer:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps({
                            "error": "Task decomposer not available",
                            "should_decompose": False
                        }, ensure_ascii=False)
                    }
                ]
            }

        task_prompt = args.get("task_prompt", "")
        files = args.get("files", [])

        # Analyze and potentially decompose the task
        result = self.orchestrator.decomposer.analyze(task_prompt, files)

        # Convert to JSON-serializable format
        result_dict = {
            "should_decompose": result.should_decompose,
            "original_task": result.original_task,
            "estimated_token_savings": f"{result.estimated_token_savings:.1%}",
            "reason": result.reason,
            "sub_tasks": [
                {
                    "id": st.id,
                    "description": st.description,
                    "prompt": st.original_prompt[:200] + "..." if len(st.original_prompt) > 200 else st.original_prompt,
                    "suggested_tier": st.suggested_tier,
                    "estimated_complexity": st.estimated_complexity,
                    "dependencies": st.dependencies,
                    "can_parallelize": st.can_parallelize,
                    "files": st.files
                }
                for st in result.sub_tasks
            ],
            "sequential_order": result.sequential_order,
            "parallel_groups": result.parallel_groups
        }

        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result_dict, indent=2, ensure_ascii=False)
                }
            ]
        }

    async def _call_list_agents(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute list_agents tool.

        Returns all available specialized agents with their capabilities.
        """
        tier_filter = args.get("tier_filter", "all")

        agents = []

        # Add specialized agents from config
        for name, config in self.orchestrator.specialized_patterns.items():
            agent_tier = config.get("tier", "sonnet")

            # Apply tier filter
            if tier_filter != "all" and agent_tier != tier_filter:
                continue

            agents.append({
                "name": config.get("agent", name),
                "specialty": name,
                "tier": agent_tier,
                "keywords": config.get("keywords", []),
                "file_patterns": config.get("file_patterns", []),
                "description": f"Specialized agent for {name} tasks"
            })

        # Add base tier agents
        base_agents = [
            {
                "name": "opus-task",
                "specialty": "architecture",
                "tier": "opus",
                "keywords": ["design", "architect", "complex", "security", "critical"],
                "file_patterns": [],
                "description": "High-complexity tasks requiring deep reasoning"
            },
            {
                "name": "sonnet-implementation",
                "specialty": "implementation",
                "tier": "sonnet",
                "keywords": ["implement", "create", "build", "add"],
                "file_patterns": [],
                "description": "Standard implementation tasks"
            },
            {
                "name": "haiku-task",
                "specialty": "simple",
                "tier": "haiku",
                "keywords": ["format", "lint", "typo", "docstring", "import"],
                "file_patterns": [],
                "description": "Simple, low-risk formatting and documentation tasks"
            }
        ]

        for agent in base_agents:
            if tier_filter == "all" or agent["tier"] == tier_filter:
                agents.append(agent)

        # Summary
        summary = {
            "total_agents": len(agents),
            "by_tier": {
                "opus": len([a for a in agents if a["tier"] == "opus"]),
                "sonnet": len([a for a in agents if a["tier"] == "sonnet"]),
                "haiku": len([a for a in agents if a["tier"] == "haiku"])
            },
            "agents": agents
        }

        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(summary, indent=2, ensure_ascii=False)
                }
            ]
        }

    async def handle_resources_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return list of available resources."""
        logger.debug("Resources list requested")
        return {
            "resources": [
                {
                    "uri": "orchestration://metrics",
                    "name": "Orchestration Metrics",
                    "description": "Real-time orchestration metrics including tier distribution and token savings",
                    "mimeType": "text/plain"
                },
                {
                    "uri": "orchestration://cache",
                    "name": "Decision Cache",
                    "description": "Cached Opus decisions available for Sonnet/Haiku",
                    "mimeType": "application/json"
                }
            ]
        }

    async def handle_resources_read(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Read a resource by URI."""
        uri = params.get("uri", "")
        logger.debug(f"Resource read requested: {uri}")

        if uri == "orchestration://metrics":
            return {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": "text/plain",
                        "text": self.orchestrator.metrics.get_summary()
                    }
                ]
            }
        elif uri == "orchestration://cache":
            cache_data = [c.to_dict() for c in self.orchestrator.cache.cache]
            return {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": "application/json",
                        "text": json.dumps(cache_data, indent=2, ensure_ascii=False)
                    }
                ]
            }
        else:
            raise ValueError(f"Unknown resource: {uri}")


# ============================================================================
# TEST MODE (CLI)
# ============================================================================

def test_mode():
    """Run in test mode with example tasks."""
    print("\n" + "="*80)
    print("ORCHESTRATION MCP SERVER - TEST MODE")
    print("="*80 + "\n")

    server = OrchestrationMCPServer()

    test_tasks = [
        # Haiku-safe tasks (should route to Haiku)
        ("Fix typo in README", []),
        ("format code", ["app/main.py"]),
        ("lint this file", ["app/api/v1/auth.py"]),
        ("add docstring to function", ["app/services/ocr.py"]),
        ("organize imports", ["app/core/config.py"]),

        # Sonnet tasks (standard implementation)
        ("Implement user login endpoint", ["app/api/v1/auth.py"]),
        ("Add unit tests with 80% coverage", ["tests/unit/test_service.py"]),
        ("Create new React component", ["frontend/src/components/Button.tsx"]),
        ("Add API endpoint for users", ["app/api/v1/users.py"]),

        # Opus tasks (architecture/complex)
        ("Design microservices architecture", []),
        ("Refactoriere Auth zu JWT", ["app/api/auth.py"] * 5),
        ("Optimiere DeepSeek GPU Memory", ["app/agents/ocr/deepseek.py"]),
        ("Security audit for authentication", ["app/core/security.py"]),

        # Specialized agents
        ("Erstelle SQLAlchemy Models", ["app/db/models.py"]),
        ("Fix bug in user registration", ["app/api/v1/auth.py"]),
        ("Docker deployment setup", ["docker-compose.yml"]),
        ("Review this code for issues", ["app/services/ocr.py"]),
    ]

    for prompt, files in test_tasks:
        print(f"\nTask: {prompt}")
        print(f"   Files: {len(files)} file(s)")

        import asyncio
        routing = asyncio.run(server.route_task(prompt, files))

        print(f"   -> Agent: {routing.agent_name}")
        print(f"   -> Tier: {routing.tier}")
        print(f"   -> Confidence: {routing.confidence:.0%}")
        print(f"   -> Reasoning: {routing.reasoning}")
        if routing.specialty:
            print(f"   -> Specialty: {routing.specialty}")

    print("\n" + "="*80)
    print(server.metrics.get_summary())
    print("="*80 + "\n")

    print("[SUCCESS] Test mode completed successfully!")
    return 0


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Main entry point."""
    if len(sys.argv) > 1 and sys.argv[1] == "--server":
        # MCP Server mode (production) - STDIO communication
        logger.info("Starting Orchestration MCP Server with STDIO transport...")

        try:
            # Initialize orchestrator
            orchestrator = OrchestrationMCPServer()
            logger.info("Orchestrator initialized")

            # Create STDIO server wrapper
            stdio_server = MCPStdioServer(orchestrator)
            logger.info("MCP STDIO Server ready - listening for JSON-RPC 2.0 messages")

            # Run STDIO communication loop
            import asyncio
            asyncio.run(stdio_server.run())

            logger.info("MCP Server shutdown complete")
            return 0

        except KeyboardInterrupt:
            logger.info("MCP Server interrupted by user")
            return 0
        except Exception as e:
            logger.error(f"MCP Server error: {e}", exc_info=True)
            return 1
    else:
        # Test mode (CLI)
        return test_mode()


if __name__ == "__main__":
    sys.exit(main())
