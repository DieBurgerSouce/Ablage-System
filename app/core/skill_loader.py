"""
Skill Loader - Dynamic skill loading and management.

Loads agent skills from YAML definitions and makes them
available to the orchestration system.

Priority: P1
Created: 2024-11-25
"""

import asyncio
import importlib
import inspect
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

import structlog
import yaml
from pydantic import BaseModel, Field, field_validator

from app.agents.base import BaseAgent
from app.core.hooks import BaseHook, HookRegistry, HookType

logger = structlog.get_logger(__name__)


# =============================================================================
# PYDANTIC MODELS
# =============================================================================


class SkillParameterDef(BaseModel):
    """Skill parameter definition."""

    name: str
    type: str = Field(..., description="Parameter type (str, int, bool, etc.)")
    required: bool = True
    default: Union[str, int, float, bool, list, dict, None] = None
    description: str = ""

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        """Validate parameter type."""
        allowed_types = ["str", "int", "float", "bool", "list", "dict", "any"]
        if v not in allowed_types:
            raise ValueError(f"Invalid parameter type: {v}. Allowed: {allowed_types}")
        return v


class SkillDefinition(BaseModel):
    """Skill definition from YAML."""

    name: str = Field(..., description="Skill name (e.g. 'ocr_document')")
    version: str = Field(default="1.0", description="Skill version")
    category: str = Field(..., description="Skill category (ocr, preprocessing, etc.)")
    description: str = ""

    # Execution
    handler: str = Field(
        ...,
        description="Python path to handler function (e.g. 'app.agents.ocr.deepseek_agent:DeepSeekAgent')",
    )
    async_execution: bool = True

    # Parameters
    parameters: List[SkillParameterDef] = Field(default_factory=list)

    # Hooks
    pre_hooks: List[str] = Field(default_factory=list, description="Pre-execution hook names")
    post_hooks: List[str] = Field(default_factory=list, description="Post-execution hook names")
    error_hooks: List[str] = Field(default_factory=list, description="Error hook names")

    # Requirements
    gpu_required: bool = False
    vram_gb: int = 0
    dependencies: List[str] = Field(default_factory=list)

    # Metadata
    author: str = ""
    tags: List[str] = Field(default_factory=list)
    enabled: bool = True


class LoadedSkill:
    """Loaded skill ready for execution."""

    def __init__(
        self,
        definition: SkillDefinition,
        handler: Callable,
        agent_instance: Optional[BaseAgent] = None,
    ):
        self.definition = definition
        self.handler = handler
        self.agent_instance = agent_instance
        self.logger = structlog.get_logger(f"skill.{definition.name}")

    async def execute(
        self, parameters: Dict[str, Any], context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Execute skill with hooks and error handling."""
        context = context or {}
        context["skill_name"] = self.definition.name

        self.logger.info(
            "skill_executing",
            skill=self.definition.name,
            parameters=parameters,
        )

        try:
            # Execute pre-hooks
            hook_registry = HookRegistry.get_instance()  # Use singleton instance!
            for hook_name in self.definition.pre_hooks:
                context = await hook_registry.execute_hook_by_name(hook_name, context)

            # Validate parameters
            self._validate_parameters(parameters)

            # Execute handler
            if self.agent_instance:
                # Agent-based skill
                result = await self.agent_instance.execute(
                    input_data=parameters, context=context
                )
            else:
                # Function-based skill
                if self.definition.async_execution:
                    result = await self.handler(**parameters)
                else:
                    result = self.handler(**parameters)

            # Execute post-hooks
            context["result"] = result
            for hook_name in self.definition.post_hooks:
                context = await hook_registry.execute_hook_by_name(hook_name, context)

            self.logger.info(
                "skill_executed",
                skill=self.definition.name,
                status="success",
            )

            return result

        except Exception as e:
            self.logger.error(
                "skill_execution_failed",
                skill=self.definition.name,
                error=str(e),
                exc_info=True,
            )

            # Execute error hooks
            context["error"] = e
            hook_registry = HookRegistry.get_instance()  # Use singleton instance!
            for hook_name in self.definition.error_hooks:
                await hook_registry.execute_hook_by_name(hook_name, context)

            raise

    def _validate_parameters(self, parameters: Dict[str, Any]) -> None:
        """Validate skill parameters."""
        for param_def in self.definition.parameters:
            param_name = param_def.name

            # Check required parameters
            if param_def.required and param_name not in parameters:
                if param_def.default is not None:
                    parameters[param_name] = param_def.default
                else:
                    raise ValueError(f"Missing required parameter: {param_name}")

            # Type validation (basic)
            if param_name in parameters:
                value = parameters[param_name]
                expected_type = param_def.type

                if expected_type == "str" and not isinstance(value, str):
                    raise TypeError(f"Parameter {param_name} must be str, got {type(value)}")
                elif expected_type == "int" and not isinstance(value, int):
                    raise TypeError(f"Parameter {param_name} must be int, got {type(value)}")
                elif expected_type == "bool" and not isinstance(value, bool):
                    raise TypeError(f"Parameter {param_name} must be bool, got {type(value)}")
                elif expected_type == "list" and not isinstance(value, list):
                    raise TypeError(f"Parameter {param_name} must be list, got {type(value)}")
                elif expected_type == "dict" and not isinstance(value, dict):
                    raise TypeError(f"Parameter {param_name} must be dict, got {type(value)}")


# =============================================================================
# SKILL LOADER
# =============================================================================


class SkillLoader:
    """
    Load and manage agent skills.

    Skills can be defined in YAML files and loaded dynamically.
    Supports both agent-based and function-based skills.
    """

    def __init__(self, skills_dir: Path = Path("Skills")):
        self.skills_dir = skills_dir
        self.loaded_skills: Dict[str, LoadedSkill] = {}
        self.logger = structlog.get_logger(__name__)

    async def load_all_skills(self) -> None:
        """Load all skills from the skills directory."""
        if not self.skills_dir.exists():
            self.logger.warning(
                "skills_directory_not_found",
                path=str(self.skills_dir),
            )
            return

        self.logger.info("loading_skills", directory=str(self.skills_dir))

        # Find all YAML files
        yaml_files = list(self.skills_dir.rglob("*.yaml")) + list(
            self.skills_dir.rglob("*.yml")
        )

        for yaml_file in yaml_files:
            try:
                await self.load_skill_from_file(yaml_file)
            except Exception as e:
                self.logger.error(
                    "skill_load_failed",
                    file=str(yaml_file),
                    error=str(e),
                    exc_info=True,
                )

        self.logger.info(
            "skills_loaded",
            total_skills=len(self.loaded_skills),
            skills=list(self.loaded_skills.keys()),
        )

    async def load_skill_from_file(self, yaml_file: Path) -> None:
        """Load a skill from a YAML file."""
        self.logger.debug("loading_skill_file", file=str(yaml_file))

        # Read YAML
        with open(yaml_file, "r", encoding="utf-8") as f:
            skill_data = yaml.safe_load(f)

        # Parse definition
        skill_def = SkillDefinition(**skill_data)

        if not skill_def.enabled:
            self.logger.info(
                "skill_disabled",
                skill=skill_def.name,
            )
            return

        # Load handler
        handler, agent_instance = await self._load_handler(skill_def.handler)

        # Create loaded skill
        loaded_skill = LoadedSkill(
            definition=skill_def,
            handler=handler,
            agent_instance=agent_instance,
        )

        # Register
        self.loaded_skills[skill_def.name] = loaded_skill

        self.logger.info(
            "skill_loaded",
            skill=skill_def.name,
            version=skill_def.version,
            category=skill_def.category,
        )

    async def _load_handler(self, handler_path: str) -> tuple[Callable, Optional[BaseAgent]]:
        """
        Load handler from Python path.

        Supports:
        - Agent classes: 'app.agents.ocr.deepseek_agent:DeepSeekAgent'
        - Functions: 'app.services.ocr_service:process_document'

        Returns:
            (handler_callable, agent_instance or None)
        """
        # Parse path
        if ":" not in handler_path:
            raise ValueError(f"Invalid handler path: {handler_path}. Expected 'module:class/function'")

        module_path, obj_name = handler_path.split(":", 1)

        # Import module
        try:
            module = importlib.import_module(module_path)
        except ImportError as e:
            raise ImportError(f"Failed to import module {module_path}: {e}") from e

        # Get object
        if not hasattr(module, obj_name):
            raise AttributeError(f"Module {module_path} has no attribute {obj_name}")

        obj = getattr(module, obj_name)

        # Check if it's an agent class
        if inspect.isclass(obj) and issubclass(obj, BaseAgent):
            # Instantiate agent
            agent_instance = obj()
            handler = agent_instance.execute
            return handler, agent_instance

        # Check if it's a callable (function)
        elif callable(obj):
            return obj, None

        else:
            raise TypeError(f"Handler {handler_path} is not a class or function")

    async def execute_skill(
        self,
        skill_name: str,
        parameters: Dict[str, Any],
        context: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Execute a loaded skill."""
        if skill_name not in self.loaded_skills:
            raise ValueError(f"Skill not found: {skill_name}")

        skill = self.loaded_skills[skill_name]
        return await skill.execute(parameters, context)

    def get_skill(self, skill_name: str) -> Optional[LoadedSkill]:
        """Get a loaded skill by name."""
        return self.loaded_skills.get(skill_name)

    def list_skills(self, category: Optional[str] = None) -> List[SkillDefinition]:
        """List all loaded skills, optionally filtered by category."""
        skills = [skill.definition for skill in self.loaded_skills.values()]

        if category:
            skills = [s for s in skills if s.category == category]

        return skills

    def get_skill_info(self, skill_name: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a skill."""
        skill = self.get_skill(skill_name)
        if not skill:
            return None

        return {
            "name": skill.definition.name,
            "version": skill.definition.version,
            "category": skill.definition.category,
            "description": skill.definition.description,
            "parameters": [
                {
                    "name": p.name,
                    "type": p.type,
                    "required": p.required,
                    "default": p.default,
                    "description": p.description,
                }
                for p in skill.definition.parameters
            ],
            "gpu_required": skill.definition.gpu_required,
            "vram_gb": skill.definition.vram_gb,
            "dependencies": skill.definition.dependencies,
            "author": skill.definition.author,
            "tags": skill.definition.tags,
            "enabled": skill.definition.enabled,
        }


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_skill_loader_instance: Optional[SkillLoader] = None
_skill_loader_lock: Optional[Any] = None  # Threading lock for singleton


def get_skill_loader() -> SkillLoader:
    """Get global SkillLoader instance (Singleton, thread-safe)."""
    global _skill_loader_instance, _skill_loader_lock

    # First check without lock (fast path)
    if _skill_loader_instance is not None:
        return _skill_loader_instance

    # Initialize lock if needed
    if _skill_loader_lock is None:
        import threading
        _skill_loader_lock = threading.Lock()

    # Second check with lock (slow path)
    with _skill_loader_lock:
        # Double-check after acquiring lock
        if _skill_loader_instance is None:
            _skill_loader_instance = SkillLoader()

    return _skill_loader_instance


async def initialize_skills() -> None:
    """Initialize and load all skills."""
    loader = get_skill_loader()
    await loader.load_all_skills()
