#!/usr/bin/env python3
"""
Task Decomposition Engine für intelligentes Task-Splitting.

Zerlegt große/komplexe Tasks in kleinere Sub-Tasks, die parallel
oder von unterschiedlichen Modellen (Haiku/Sonnet/Opus) bearbeitet werden können.

Features:
- Automatische Erkennung von zusammengesetzten Tasks
- Dependency Graph für Sub-Tasks
- Parallelisierbare Tasks identifizieren
- Token-effiziente Aufteilung
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from enum import Enum

logger = logging.getLogger("orchestration.decomposer")


class TaskPriority(Enum):
    """Priority levels for sub-tasks."""
    CRITICAL = 1  # Must complete first
    HIGH = 2      # Important, but can wait
    NORMAL = 3    # Standard priority
    LOW = 4       # Can run last or in background


@dataclass
class SubTask:
    """A decomposed sub-task."""
    id: str
    description: str
    original_prompt: str
    suggested_tier: str  # haiku, sonnet, opus
    priority: TaskPriority
    estimated_complexity: float  # 0.0 - 1.0
    dependencies: List[str] = field(default_factory=list)  # IDs of tasks that must complete first
    files: List[str] = field(default_factory=list)
    can_parallelize: bool = True
    keywords: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "description": self.description,
            "original_prompt": self.original_prompt,
            "suggested_tier": self.suggested_tier,
            "priority": self.priority.name,
            "estimated_complexity": self.estimated_complexity,
            "dependencies": self.dependencies,
            "files": self.files,
            "can_parallelize": self.can_parallelize,
            "keywords": self.keywords
        }


@dataclass
class DecompositionResult:
    """Result of task decomposition."""
    original_task: str
    should_decompose: bool
    reason: str
    sub_tasks: List[SubTask] = field(default_factory=list)
    parallel_groups: List[List[str]] = field(default_factory=list)  # Groups of task IDs that can run in parallel
    sequential_order: List[str] = field(default_factory=list)  # Final execution order
    estimated_token_savings: float = 0.0  # Percentage

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "original_task": self.original_task,
            "should_decompose": self.should_decompose,
            "reason": self.reason,
            "sub_tasks": [st.to_dict() for st in self.sub_tasks],
            "parallel_groups": self.parallel_groups,
            "sequential_order": self.sequential_order,
            "estimated_token_savings": self.estimated_token_savings
        }


class TaskDecomposer:
    """Engine für intelligentes Task-Splitting."""

    # Patterns die auf zusammengesetzte Tasks hinweisen
    COMPOSITE_PATTERNS = [
        # Multiple actions
        (r'\band\b.*\band\b', 'multiple_ands'),
        (r',.*,.*,', 'multiple_commas'),
        (r'\bthen\b', 'sequential_then'),
        (r'\bfirst\b.*\bthen\b', 'first_then'),
        (r'\bafter\b', 'sequential_after'),

        # Implementation + Testing
        (r'\bimplement.*\btest', 'impl_with_test'),
        (r'\bcreate.*\btest', 'create_with_test'),
        (r'\badd.*\btest', 'add_with_test'),

        # Multiple file indicators
        (r'\bfiles?\b.*\bfiles?\b', 'multiple_files'),
        (r'\ball\b.*\bfiles?\b', 'all_files'),
        (r'\bevery\b.*\b(file|component|module)', 'every_file'),

        # Complex patterns
        (r'\brefactor.*\band\b.*\bupdate', 'refactor_update'),
        (r'\bmigrate.*\bto\b', 'migration'),
        (r'\bredesign', 'redesign'),
    ]

    # Keywords für Tier-Zuordnung
    TIER_KEYWORDS = {
        "haiku": ["format", "lint", "typo", "comment", "docstring", "import", "whitespace"],
        "sonnet": ["implement", "create", "add", "build", "endpoint", "component", "test"],
        "opus": ["design", "architecture", "refactor", "migrate", "security", "optimize"]
    }

    # Min/Max Grenzen
    MIN_TASK_LENGTH = 50  # Zu kurz für Decomposition
    MIN_SUBTASKS = 2      # Mindestens 2 Sub-Tasks für sinnvolle Zerlegung
    MAX_SUBTASKS = 8      # Nicht zu viele Sub-Tasks

    def analyze(self, task_prompt: str, files: Optional[List[str]] = None) -> DecompositionResult:
        """Analysiere Task und entscheide ob Decomposition sinnvoll ist.

        Args:
            task_prompt: Der ursprüngliche Task
            files: Optional list of affected files

        Returns:
            DecompositionResult with analysis
        """
        files = files or []
        task_lower = task_prompt.lower()

        # 1. Check if task is too short
        if len(task_prompt) < self.MIN_TASK_LENGTH:
            return DecompositionResult(
                original_task=task_prompt,
                should_decompose=False,
                reason="Task too short for decomposition"
            )

        # 2. Check for composite patterns
        detected_patterns = []
        for pattern, name in self.COMPOSITE_PATTERNS:
            if re.search(pattern, task_lower):
                detected_patterns.append(name)

        # 3. Check file count
        file_based_decomposition = len(files) >= 3

        # 4. Decide if decomposition is beneficial
        should_decompose = (
            len(detected_patterns) >= 1 or
            file_based_decomposition or
            len(task_prompt) > 500  # Long prompts often benefit
        )

        if not should_decompose:
            return DecompositionResult(
                original_task=task_prompt,
                should_decompose=False,
                reason="No decomposition patterns detected"
            )

        # 5. Decompose the task
        sub_tasks = self._decompose_task(task_prompt, files, detected_patterns)

        if len(sub_tasks) < self.MIN_SUBTASKS:
            return DecompositionResult(
                original_task=task_prompt,
                should_decompose=False,
                reason="Not enough meaningful sub-tasks"
            )

        # 6. Build dependency graph and parallel groups
        parallel_groups, sequential_order = self._build_execution_plan(sub_tasks)

        # 7. Estimate token savings
        token_savings = self._estimate_token_savings(sub_tasks)

        return DecompositionResult(
            original_task=task_prompt,
            should_decompose=True,
            reason=f"Detected patterns: {detected_patterns}" if detected_patterns else "File-based decomposition",
            sub_tasks=sub_tasks,
            parallel_groups=parallel_groups,
            sequential_order=sequential_order,
            estimated_token_savings=token_savings
        )

    def _decompose_task(
        self,
        task_prompt: str,
        files: List[str],
        patterns: List[str]
    ) -> List[SubTask]:
        """Decompose task into sub-tasks based on detected patterns."""
        sub_tasks: List[SubTask] = []
        task_lower = task_prompt.lower()

        # Strategy 1: Implementation + Testing pattern
        if any(p in patterns for p in ['impl_with_test', 'create_with_test', 'add_with_test']):
            sub_tasks.extend(self._split_impl_test(task_prompt, files))

        # Strategy 2: Sequential patterns (first...then, after)
        elif any(p in patterns for p in ['first_then', 'sequential_then', 'sequential_after']):
            sub_tasks.extend(self._split_sequential(task_prompt, files))

        # Strategy 3: Multiple actions (and...and, commas)
        elif any(p in patterns for p in ['multiple_ands', 'multiple_commas']):
            sub_tasks.extend(self._split_by_actions(task_prompt, files))

        # Strategy 4: File-based decomposition
        elif len(files) >= 3:
            sub_tasks.extend(self._split_by_files(task_prompt, files))

        # Strategy 5: Generic decomposition for long tasks
        else:
            sub_tasks.extend(self._split_generic(task_prompt, files))

        # Post-process: Add formatting/cleanup tasks for Haiku
        if sub_tasks:
            sub_tasks.extend(self._add_haiku_tasks(sub_tasks))

        # Limit sub-tasks
        return sub_tasks[:self.MAX_SUBTASKS]

    def _split_impl_test(self, task_prompt: str, files: List[str]) -> List[SubTask]:
        """Zerlegt einen Task mit Implementation und Tests in Sub-Tasks.

        Erstellt drei Sub-Tasks in folgender Reihenfolge:
        1. Design/Plan (Opus bei hoher Komplexität, sonst Sonnet)
        2. Implementation (Sonnet)
        3. Tests (Sonnet, abhängig von Implementation)

        Args:
            task_prompt: Der ursprüngliche Task-Prompt
            files: Liste der betroffenen Dateien

        Returns:
            Liste von SubTask-Objekten mit korrekten Dependencies
        """
        sub_tasks = []

        # Extract implementation part
        impl_match = re.search(r'(implement|create|add|build)\s+([^,]+?)(?:\s+and\s+|\s+with\s+|,)', task_prompt, re.I)
        impl_desc = impl_match.group(2).strip() if impl_match else "the feature"

        # 1. Design/Plan (Opus if complex)
        complexity = 0.7 if len(task_prompt) > 300 else 0.5
        sub_tasks.append(SubTask(
            id="design",
            description=f"Design architecture for {impl_desc}",
            original_prompt=f"Plan the implementation approach for: {impl_desc}",
            suggested_tier="opus" if complexity > 0.6 else "sonnet",
            priority=TaskPriority.CRITICAL,
            estimated_complexity=complexity,
            dependencies=[],
            files=files,
            can_parallelize=False
        ))

        # 2. Implementation (Sonnet)
        impl_files = [f for f in files if not f.startswith("test")]
        sub_tasks.append(SubTask(
            id="implement",
            description=f"Implement {impl_desc}",
            original_prompt=f"Implement: {impl_desc}",
            suggested_tier="sonnet",
            priority=TaskPriority.HIGH,
            estimated_complexity=0.6,
            dependencies=["design"],
            files=impl_files,
            can_parallelize=False
        ))

        # 3. Tests (Sonnet, can run after impl)
        test_files = [f for f in files if f.startswith("test") or "test" in f]
        sub_tasks.append(SubTask(
            id="test",
            description=f"Write tests for {impl_desc}",
            original_prompt=f"Write comprehensive tests for: {impl_desc}",
            suggested_tier="sonnet",
            priority=TaskPriority.NORMAL,
            estimated_complexity=0.5,
            dependencies=["implement"],
            files=test_files or ["tests/"],
            can_parallelize=False
        ))

        return sub_tasks

    def _split_sequential(self, task_prompt: str, files: List[str]) -> List[SubTask]:
        """Zerlegt sequentielle Tasks basierend auf Schlüsselwörtern.

        Erkennt Patterns wie "first...then", "after" und erstellt
        entsprechend verkettete Sub-Tasks mit Dependencies.

        Args:
            task_prompt: Der ursprüngliche Task-Prompt
            files: Liste der betroffenen Dateien

        Returns:
            Liste von SubTask-Objekten in sequentieller Reihenfolge
        """
        sub_tasks = []

        # Split by "then", "after", "first"
        parts = re.split(r'\s*(?:then|after|first)\s*', task_prompt, flags=re.I)
        parts = [p.strip() for p in parts if p.strip()]

        for i, part in enumerate(parts):
            tier = self._detect_tier(part)
            sub_tasks.append(SubTask(
                id=f"step_{i+1}",
                description=part[:100],
                original_prompt=part,
                suggested_tier=tier,
                priority=TaskPriority(min(i + 1, 4)),
                estimated_complexity=0.5,
                dependencies=[f"step_{i}"] if i > 0 else [],
                files=files,
                can_parallelize=False,
                keywords=self._extract_keywords(part)
            ))

        return sub_tasks

    def _split_by_actions(self, task_prompt: str, files: List[str]) -> List[SubTask]:
        """Zerlegt Tasks mit mehreren Aktionen (and, Kommas).

        Erkennt unabhängige Aktionen und erstellt parallelisierbare
        Sub-Tasks, sofern keine sequentiellen Abhängigkeiten erkannt werden.

        Args:
            task_prompt: Der ursprüngliche Task-Prompt
            files: Liste der betroffenen Dateien

        Returns:
            Liste von SubTask-Objekten (parallelisierbar wenn unabhängig)
        """
        sub_tasks = []

        # Split by "and" or commas
        parts = re.split(r'\s*(?:,\s*and|\s+and\s+|,)\s*', task_prompt, flags=re.I)
        parts = [p.strip() for p in parts if p.strip() and len(p) > 10]

        # Check if parts are independent (can parallelize)
        independent = not any(word in task_prompt.lower() for word in ['then', 'after', 'before', 'first'])

        for i, part in enumerate(parts):
            tier = self._detect_tier(part)
            sub_tasks.append(SubTask(
                id=f"action_{i+1}",
                description=part[:100],
                original_prompt=part,
                suggested_tier=tier,
                priority=TaskPriority.NORMAL,
                estimated_complexity=0.4,
                dependencies=[],  # Independent actions
                files=files,
                can_parallelize=independent,
                keywords=self._extract_keywords(part)
            ))

        return sub_tasks

    def _split_by_files(self, task_prompt: str, files: List[str]) -> List[SubTask]:
        """Zerlegt Tasks nach Datei-Gruppen bei vielen betroffenen Dateien.

        Gruppiert Dateien nach Verzeichnis und erstellt für jede Gruppe
        einen parallelisierbaren Sub-Task mit dem gleichen Tier.

        Args:
            task_prompt: Der ursprüngliche Task-Prompt
            files: Liste der betroffenen Dateien (mind. 3 für Zerlegung)

        Returns:
            Liste von SubTask-Objekten (parallelisierbar nach Datei-Gruppe)
        """
        sub_tasks = []
        tier = self._detect_tier(task_prompt)

        # Group files by directory or type
        file_groups = self._group_files(files)

        for i, (group_name, group_files) in enumerate(file_groups.items()):
            sub_tasks.append(SubTask(
                id=f"file_group_{i+1}",
                description=f"{task_prompt[:50]}... in {group_name}",
                original_prompt=f"{task_prompt}\n\nFocus on files in: {group_name}",
                suggested_tier=tier,
                priority=TaskPriority.NORMAL,
                estimated_complexity=0.4,
                dependencies=[],  # File groups are independent
                files=group_files,
                can_parallelize=True,
                keywords=self._extract_keywords(task_prompt)
            ))

        return sub_tasks

    def _split_generic(self, task_prompt: str, files: List[str]) -> List[SubTask]:
        """Generische Zerlegung für lange Tasks ohne spezifische Patterns.

        Teilt den Task nach Sätzen auf und erstellt für jeden Satz
        (> 20 Zeichen) einen separaten Sub-Task.

        Args:
            task_prompt: Der ursprüngliche Task-Prompt
            files: Liste der betroffenen Dateien

        Returns:
            Liste von SubTask-Objekten oder leere Liste wenn nicht zerlegbar
        """
        sub_tasks = []

        # Split by sentences
        sentences = re.split(r'[.!?]\s+', task_prompt)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 20]

        if len(sentences) < 2:
            # Can't split meaningfully
            return []

        for i, sentence in enumerate(sentences):
            tier = self._detect_tier(sentence)
            sub_tasks.append(SubTask(
                id=f"part_{i+1}",
                description=sentence[:100],
                original_prompt=sentence,
                suggested_tier=tier,
                priority=TaskPriority.NORMAL,
                estimated_complexity=0.5,
                dependencies=[],
                files=files,
                can_parallelize=True,
                keywords=self._extract_keywords(sentence)
            ))

        return sub_tasks

    def _add_haiku_tasks(self, existing_tasks: List[SubTask]) -> List[SubTask]:
        """Fügt Haiku-Level Cleanup-Tasks nach der Hauptarbeit hinzu.

        Erstellt einen Formatierungs-Task (Haiku-Tier) der nach allen
        anderen Tasks ausgeführt wird und alle modifizierten Dateien
        formatiert und Imports organisiert.

        Args:
            existing_tasks: Liste der bereits erstellten Sub-Tasks

        Returns:
            Liste mit Haiku-Cleanup-Tasks (aktuell: Format-Task)
        """
        haiku_tasks = []

        # Get all files from existing tasks
        all_files = set()
        for task in existing_tasks:
            all_files.update(task.files)

        # Add formatting task
        if all_files:
            haiku_tasks.append(SubTask(
                id="format",
                description="Format code and organize imports",
                original_prompt="Format all modified files and organize imports",
                suggested_tier="haiku",
                priority=TaskPriority.LOW,
                estimated_complexity=0.1,
                dependencies=[t.id for t in existing_tasks],  # Run after all others
                files=list(all_files),
                can_parallelize=False
            ))

        return haiku_tasks

    def _detect_tier(self, text: str) -> str:
        """Ermittelt den passenden Tier basierend auf Keywords.

        Zählt Keyword-Matches für jeden Tier (Haiku, Sonnet, Opus)
        und gibt den Tier mit den meisten Matches zurück.

        Args:
            text: Der zu analysierende Text

        Returns:
            Tier-Name ('haiku', 'sonnet' oder 'opus'), Default: 'sonnet'
        """
        text_lower = text.lower()

        # Count keyword matches
        scores = {tier: 0 for tier in self.TIER_KEYWORDS}
        for tier, keywords in self.TIER_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    scores[tier] += 1

        # Return tier with highest score, default to sonnet
        max_tier = max(scores, key=scores.get)
        return max_tier if scores[max_tier] > 0 else "sonnet"

    def _extract_keywords(self, text: str) -> List[str]:
        """Extrahiert relevante Keywords aus dem Text.

        Durchsucht den Text nach allen bekannten Tier-Keywords
        und sammelt gefundene Matches.

        Args:
            text: Der zu analysierende Text

        Returns:
            Liste der gefundenen Keywords
        """
        keywords = []
        text_lower = text.lower()

        for tier_keywords in self.TIER_KEYWORDS.values():
            for kw in tier_keywords:
                if kw in text_lower:
                    keywords.append(kw)

        return keywords

    def _group_files(self, files: List[str]) -> Dict[str, List[str]]:
        """Gruppiert Dateien nach Verzeichnis.

        Extrahiert das oberste Verzeichnis aus jedem Dateipfad
        und gruppiert alle Dateien entsprechend.

        Args:
            files: Liste der Dateipfade

        Returns:
            Dictionary mit Verzeichnisname als Key und Dateien als Values
        """
        groups: Dict[str, List[str]] = {}

        for file_path in files:
            # Extract directory
            parts = file_path.replace("\\", "/").split("/")
            if len(parts) > 1:
                group_key = parts[0] if parts[0] not in [".", ""] else parts[1] if len(parts) > 1 else "root"
            else:
                group_key = "root"

            if group_key not in groups:
                groups[group_key] = []
            groups[group_key].append(file_path)

        return groups

    def _build_execution_plan(
        self,
        sub_tasks: List[SubTask]
    ) -> Tuple[List[List[str]], List[str]]:
        """Build execution plan with parallel groups and sequential order.

        Returns:
            Tuple of (parallel_groups, sequential_order)
        """
        # Build dependency graph
        task_map = {t.id: t for t in sub_tasks}
        remaining = set(t.id for t in sub_tasks)
        completed: Set[str] = set()
        parallel_groups: List[List[str]] = []
        sequential_order: List[str] = []

        while remaining:
            # Find tasks with all dependencies satisfied
            ready = []
            for task_id in remaining:
                task = task_map[task_id]
                deps_satisfied = all(d in completed for d in task.dependencies)
                if deps_satisfied:
                    ready.append(task_id)

            if not ready:
                # Circular dependency or error - add remaining in order
                ready = list(remaining)

            # Group parallelizable tasks
            parallel_group = [tid for tid in ready if task_map[tid].can_parallelize]
            sequential_tasks = [tid for tid in ready if not task_map[tid].can_parallelize]

            # Add parallel group
            if len(parallel_group) > 1:
                parallel_groups.append(parallel_group)
                sequential_order.extend(parallel_group)
            elif parallel_group:
                sequential_order.extend(parallel_group)

            # Add sequential tasks
            sequential_order.extend(sequential_tasks)

            # Mark as completed
            completed.update(ready)
            remaining -= set(ready)

        return parallel_groups, sequential_order

    def _estimate_token_savings(self, sub_tasks: List[SubTask]) -> float:
        """Schätzt Token-Einsparungen durch die Zerlegung.

        Berechnet prozentuale Einsparungen basierend auf Tier-Verteilung.
        Kostenverhältnisse: Haiku=1, Sonnet=5, Opus=15

        Args:
            sub_tasks: Liste der zerlegten Sub-Tasks

        Returns:
            Geschätzte Einsparung in Prozent (0.0-100.0)
        """
        if not sub_tasks:
            return 0.0

        # Calculate potential savings
        haiku_tasks = sum(1 for t in sub_tasks if t.suggested_tier == "haiku")
        sonnet_tasks = sum(1 for t in sub_tasks if t.suggested_tier == "sonnet")
        opus_tasks = sum(1 for t in sub_tasks if t.suggested_tier == "opus")

        total = len(sub_tasks)
        if total == 0:
            return 0.0

        # Token cost ratios (relative to Opus)
        # Haiku: ~1/15 of Opus, Sonnet: ~1/3 of Opus
        baseline_opus_cost = total * 15.0  # All tasks with Opus
        actual_cost = (haiku_tasks * 1.0) + (sonnet_tasks * 5.0) + (opus_tasks * 15.0)

        savings = (baseline_opus_cost - actual_cost) / baseline_opus_cost
        return round(savings * 100, 1)


# Test mode
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    decomposer = TaskDecomposer()

    test_tasks = [
        ("Implement user authentication and write tests for it", ["app/auth.py", "tests/test_auth.py"]),
        ("First design the API, then implement endpoints, then add documentation", ["app/api/users.py"]),
        ("Add login, registration, and password reset features", ["app/auth.py"]),
        ("Refactor the entire OCR module and update tests", ["app/ocr.py"] * 5),
        ("Fix typo", []),  # Should NOT decompose
    ]

    print("\n" + "="*80)
    print("TASK DECOMPOSER - TEST MODE")
    print("="*80 + "\n")

    for prompt, files in test_tasks:
        print(f"\nTask: {prompt}")
        print(f"Files: {files}")

        result = decomposer.analyze(prompt, files)

        print(f"Should decompose: {result.should_decompose}")
        print(f"Reason: {result.reason}")

        if result.should_decompose:
            print(f"Sub-tasks ({len(result.sub_tasks)}):")
            for st in result.sub_tasks:
                print(f"  - [{st.suggested_tier}] {st.id}: {st.description[:60]}...")
                if st.dependencies:
                    print(f"    Depends on: {st.dependencies}")

            print(f"Parallel groups: {result.parallel_groups}")
            print(f"Execution order: {result.sequential_order}")
            print(f"Estimated token savings: {result.estimated_token_savings}%")

        print("-" * 40)

    print("\n[SUCCESS] Test completed!")
