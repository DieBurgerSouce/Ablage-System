"""
Team Spawner - Generates concrete Claude Code Task tool call instructions.

This module bridges between team_workflow.py templates and actual agent spawning.
It resolves prompt templates, determines parallelization, and formats spawn instructions.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
from .team_workflow import (
    ClassificationOutput,
    TeamTemplate,
    Phase,
    AgentSpec,
    PhaseMode,
    classify_task,
)


@dataclass
class SpawnInstruction:
    """Concrete instruction for spawning a single agent via Claude Code Task tool."""

    role: str
    subagent_type: str
    model: str  # haiku, sonnet, opus
    prompt: str  # Fully resolved prompt (template vars filled in)
    description: str
    run_in_background: bool


@dataclass
class PhaseSpawnPlan:
    """Spawn plan for a single phase of a team workflow."""

    phase_name: str
    phase_number: int
    mode: PhaseMode
    instructions: List[SpawnInstruction]
    gate_after: Optional[str] = None  # gate to run after this phase


@dataclass
class TeamSpawnPlan:
    """Complete spawn plan for a team workflow."""

    team_type: str
    team_name: str
    total_phases: int
    total_agents: int
    phases: List[PhaseSpawnPlan]
    has_shared_file_integration: bool = False


class TeamSpawner:
    """Generates concrete spawn instructions for team workflows."""

    def _resolve_prompt(self, template: str, task_description: str, context: Dict[str, str]) -> str:
        """Resolve a prompt template with task description and context vars."""
        # Start with task_description
        resolved = template.replace("{task_description}", task_description)

        # Replace all context placeholders
        for key, value in context.items():
            placeholder = f"{{{key}}}"
            resolved = resolved.replace(placeholder, value)

        return resolved

    def create_spawn_plan(
        self,
        classification: ClassificationOutput,
        task_description: str,
        context: Dict[str, str],
    ) -> TeamSpawnPlan:
        """Create a complete spawn plan from a classification result."""
        template = classification.template
        phase_plans: List[PhaseSpawnPlan] = []
        total_agents = 0

        for phase_idx, phase in enumerate(template.phases, start=1):
            instructions: List[SpawnInstruction] = []

            for agent in phase.agents:
                # Resolve prompt template
                prompt = self._resolve_prompt(
                    agent.prompt_template,
                    task_description,
                    context,
                )

                # Determine if background execution
                run_in_background = phase.mode == PhaseMode.PARALLEL

                instruction = SpawnInstruction(
                    role=agent.role,
                    subagent_type=agent.subagent_type,
                    model=agent.model,
                    prompt=prompt,
                    description=agent.description,
                    run_in_background=run_in_background,
                )
                instructions.append(instruction)
                total_agents += 1

            phase_plan = PhaseSpawnPlan(
                phase_name=phase.name,
                phase_number=phase_idx,
                mode=phase.mode,
                instructions=instructions,
                gate_after=phase.gate,
            )
            phase_plans.append(phase_plan)

        return TeamSpawnPlan(
            team_type=classification.team_type.value,
            team_name=template.name,
            total_phases=len(phase_plans),
            total_agents=total_agents,
            phases=phase_plans,
            has_shared_file_integration=template.requires_shared_file_integration,
        )

    def format_spawn_instructions(self, plan: TeamSpawnPlan) -> str:
        """Generate human-readable markdown with Task() call examples."""
        lines: List[str] = []

        # Header
        lines.append(f"# Team Spawn Plan: {plan.team_name}")
        lines.append(f"**Type**: {plan.team_type}")
        lines.append(f"**Total Phases**: {plan.total_phases}")
        lines.append(f"**Total Agents**: {plan.total_agents}")
        lines.append("")

        # Phase-by-phase instructions
        for phase in plan.phases:
            is_parallel = phase.mode == PhaseMode.PARALLEL
            lines.append(f"## Phase {phase.phase_number}: {phase.phase_name}")
            lines.append(f"**Mode**: {phase.mode.value.upper()}")
            lines.append(f"**Agents**: {len(phase.instructions)}")
            lines.append("")

            if is_parallel:
                lines.append("**SPAWN THESE IN ONE MESSAGE** (parallel execution):")
                lines.append("")

            for instr in phase.instructions:
                lines.append(f"### {instr.role}")
                lines.append("```python")
                lines.append("Task({")
                lines.append(f'  prompt: """{instr.prompt}""",')
                lines.append(f'  subagent_type: "{instr.subagent_type}",')
                lines.append(f'  model: "{instr.model}",')
                lines.append(f'  description: "{instr.description}",')
                if instr.run_in_background:
                    lines.append("  run_in_background: true")
                lines.append("})")
                lines.append("```")
                lines.append("")

            if is_parallel:
                lines.append("**WAIT** for all agents to complete before proceeding.")
                lines.append("")

            # Quality gate reminder
            if phase.gate_after:
                lines.append(f"**Quality Gate**: {phase.gate_after}")
                lines.append("- Review results before proceeding to next phase")
                lines.append("- Ensure quality standards met")
                lines.append("")

            lines.append("---")
            lines.append("")

        # Summary
        lines.append("## Execution Summary")
        lines.append("")
        lines.append("1. Spawn all parallel phases in ONE message")
        lines.append("2. WAIT after each parallel phase for results")
        lines.append("3. Run quality gates between phases")
        lines.append("4. Proceed sequentially through phases")

        return "\n".join(lines)

    def get_phase_instructions(self, plan: TeamSpawnPlan, phase_number: int) -> str:
        """Get instructions for a single phase (for incremental execution)."""
        if phase_number < 1 or phase_number > len(plan.phases):
            return f"ERROR: Invalid phase number {phase_number}. Valid range: 1-{len(plan.phases)}"

        phase = plan.phases[phase_number - 1]
        is_parallel = phase.mode == PhaseMode.PARALLEL
        lines: List[str] = []

        lines.append(f"# Phase {phase.phase_number}: {phase.phase_name}")
        lines.append(f"**Mode**: {phase.mode.value.upper()}")
        lines.append("")

        if is_parallel:
            lines.append("**SPAWN THESE IN ONE MESSAGE**:")
            lines.append("")

        for instr in phase.instructions:
            lines.append(f"### {instr.role}")
            lines.append("```python")
            lines.append("Task({")
            lines.append(f'  prompt: """{instr.prompt}""",')
            lines.append(f'  subagent_type: "{instr.subagent_type}",')
            lines.append(f'  model: "{instr.model}",')
            lines.append(f'  description: "{instr.description}",')
            if instr.run_in_background:
                lines.append("  run_in_background: true")
            lines.append("})")
            lines.append("```")
            lines.append("")

        if is_parallel:
            lines.append("**WAIT** for all agents to complete.")
            lines.append("")

        if phase.gate_after:
            lines.append(f"**Quality Gate**: {phase.gate_after}")
            lines.append("")

        return "\n".join(lines)


# Convenience functions

def spawn_for_task(
    task_description: str,
    affected_files: List[str],
    context: Optional[Dict[str, str]] = None,
) -> TeamSpawnPlan:
    """Classify task and create spawn plan in one call."""
    if context is None:
        context = {}

    # Add affected_files to context
    context["affected_files"] = ", ".join(affected_files)

    # Classify the task
    classification = classify_task(task_description, affected_files)

    # Create spawn plan
    spawner = TeamSpawner()
    return spawner.create_spawn_plan(classification, task_description, context)


def format_plan(plan: TeamSpawnPlan) -> str:
    """Format a spawn plan as markdown instructions."""
    spawner = TeamSpawner()
    return spawner.format_spawn_instructions(plan)


if __name__ == "__main__":
    # Example usage
    task = "Fix the OCR confidence calculation bug in DeepSeek backend"
    files = ["app/services/ocr/deepseek_service.py"]
    context = {
        "bug_description": "Confidence scores are always 1.0",
        "expected_behavior": "Confidence should reflect actual OCR quality",
    }

    plan = spawn_for_task(task, files, context)
    print(format_plan(plan))
