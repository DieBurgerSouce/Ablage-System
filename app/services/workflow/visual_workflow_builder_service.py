# -*- coding: utf-8 -*-
"""Visual Workflow Builder Service.

No-Code Workflow-Editor für Business-User.
Erstellt Drag&Drop Workflow-Definitionen mit ReactFlow-Kompatibilität.

Features:
- Pre-built Workflow-Bloecke (Genehmigung, Benachrichtigung, Bedingung, Verzögerung)
- Multi-Level Approval (sequentiell, parallel, 2-von-3)
- Workflow-Simulation (Dry-Run)
- Template-Generierung
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.workflow.workflow_service import WorkflowService

logger = structlog.get_logger(__name__)


# =============================================================================
# Enums & Data Classes
# =============================================================================


class BlockType(str, Enum):
    """Verfügbare Block-Typen für den visuellen Builder."""

    TRIGGER = "trigger"
    APPROVAL = "approval"
    NOTIFICATION = "notification"
    CONDITION = "condition"
    DELAY = "delay"
    ACTION = "action"
    PARALLEL = "parallel"
    LOOP = "loop"
    END = "end"


class ApprovalMode(str, Enum):
    """Genehmigungsmodi."""

    SINGLE = "single"  # Ein Genehmiger
    SEQUENTIAL = "sequential"  # Nacheinander
    PARALLEL = "parallel"  # Alle gleichzeitig
    THRESHOLD = "threshold"  # N von M (z.B. 2 von 3)


class TriggerType(str, Enum):
    """Verfügbare Trigger-Typen."""

    DOCUMENT_UPLOADED = "document_uploaded"
    DOCUMENT_APPROVED = "document_approved"
    INVOICE_RECEIVED = "invoice_received"
    PAYMENT_DUE = "payment_due"
    AMOUNT_THRESHOLD = "amount_threshold"
    SCHEDULE = "schedule"
    MANUAL = "manual"
    WEBHOOK = "webhook"


class ConditionOperator(str, Enum):
    """Bedingungs-Operatoren."""

    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    GREATER_OR_EQUAL = "greater_or_equal"
    LESS_OR_EQUAL = "less_or_equal"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    IS_EMPTY = "is_empty"
    IS_NOT_EMPTY = "is_not_empty"
    IN_LIST = "in_list"
    MATCHES_REGEX = "matches_regex"


class NotificationChannel(str, Enum):
    """Benachrichtigungs-Kanaele."""

    EMAIL = "email"
    SLACK = "slack"
    IN_APP = "in_app"
    SMS = "sms"


@dataclass
class WorkflowBlock:
    """Repraesentation eines Workflow-Blocks im visuellen Editor."""

    id: str
    type: BlockType
    label: str
    description: str
    config: Dict[str, Any] = field(default_factory=dict)
    position_x: float = 0.0
    position_y: float = 0.0
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    is_valid: bool = True
    validation_errors: List[str] = field(default_factory=list)


@dataclass
class WorkflowEdge:
    """Verbindung zwischen zwei Blocks."""

    id: str
    source_id: str
    target_id: str
    source_handle: Optional[str] = None  # Für bedingte Ausgaenge
    target_handle: Optional[str] = None
    label: Optional[str] = None
    condition: Optional[Dict[str, Any]] = None


@dataclass
class VisualWorkflow:
    """Vollständige visuelle Workflow-Definition."""

    id: str
    name: str
    description: Optional[str]
    blocks: List[WorkflowBlock]
    edges: List[WorkflowEdge]
    trigger_config: Dict[str, Any]
    variables: Dict[str, Any] = field(default_factory=dict)
    is_valid: bool = True
    validation_errors: List[str] = field(default_factory=list)


@dataclass
class SimulationResult:
    """Ergebnis einer Workflow-Simulation."""

    success: bool
    execution_path: List[str]  # Block-IDs in Ausführungsreihenfolge
    simulated_outputs: Dict[str, Any]
    warnings: List[str]
    errors: List[str]
    duration_estimate_seconds: int


# =============================================================================
# Block-Definitionen (Pre-built Blocks)
# =============================================================================


BLOCK_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    # Trigger-Blocks
    "trigger_document_upload": {
        "type": BlockType.TRIGGER,
        "label": "Dokument hochgeladen",
        "description": "Startet bei neuem Dokument-Upload",
        "category": "trigger",
        "icon": "upload",
        "config_schema": {
            "document_types": {"type": "array", "items": {"type": "string"}},
            "folders": {"type": "array", "items": {"type": "string"}},
        },
        "outputs": ["next"],
    },
    "trigger_invoice_received": {
        "type": BlockType.TRIGGER,
        "label": "Rechnung eingegangen",
        "description": "Startet bei eingehender Rechnung",
        "category": "trigger",
        "icon": "receipt",
        "config_schema": {
            "min_amount": {"type": "number", "optional": True},
            "max_amount": {"type": "number", "optional": True},
            "suppliers": {"type": "array", "items": {"type": "string"}, "optional": True},
        },
        "outputs": ["next"],
    },
    "trigger_schedule": {
        "type": BlockType.TRIGGER,
        "label": "Zeitplan",
        "description": "Startet nach Zeitplan (Cron)",
        "category": "trigger",
        "icon": "clock",
        "config_schema": {
            "cron": {"type": "string", "required": True},
            "timezone": {"type": "string", "default": "Europe/Berlin"},
        },
        "outputs": ["next"],
    },
    "trigger_manual": {
        "type": BlockType.TRIGGER,
        "label": "Manueller Start",
        "description": "Workflow wird manuell gestartet",
        "category": "trigger",
        "icon": "hand",
        "config_schema": {},
        "outputs": ["next"],
    },
    # Genehmigungs-Blocks
    "approval_single": {
        "type": BlockType.APPROVAL,
        "label": "Einzelgenehmigung",
        "description": "Ein Genehmiger erforderlich",
        "category": "approval",
        "icon": "check-circle",
        "config_schema": {
            "approver_id": {"type": "uuid", "optional": True},
            "approver_role": {"type": "string", "optional": True},
            "timeout_hours": {"type": "number", "default": 48},
            "reminder_hours": {"type": "number", "default": 24},
            "auto_approve_amount": {"type": "number", "optional": True},
        },
        "inputs": ["input"],
        "outputs": ["approved", "rejected", "timeout"],
    },
    "approval_sequential": {
        "type": BlockType.APPROVAL,
        "label": "Sequentielle Genehmigung",
        "description": "Mehrere Genehmiger nacheinander",
        "category": "approval",
        "icon": "list-checks",
        "config_schema": {
            "approvers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "uuid", "optional": True},
                        "role": {"type": "string", "optional": True},
                        "level": {"type": "number"},
                    },
                },
            },
            "stop_on_reject": {"type": "boolean", "default": True},
            "timeout_hours_per_level": {"type": "number", "default": 24},
        },
        "inputs": ["input"],
        "outputs": ["approved", "rejected", "timeout"],
    },
    "approval_parallel": {
        "type": BlockType.APPROVAL,
        "label": "Parallele Genehmigung",
        "description": "Alle müssen gleichzeitig genehmigen",
        "category": "approval",
        "icon": "git-merge",
        "config_schema": {
            "approvers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "uuid", "optional": True},
                        "role": {"type": "string", "optional": True},
                    },
                },
            },
            "require_all": {"type": "boolean", "default": True},
            "timeout_hours": {"type": "number", "default": 48},
        },
        "inputs": ["input"],
        "outputs": ["approved", "rejected", "timeout"],
    },
    "approval_threshold": {
        "type": BlockType.APPROVAL,
        "label": "Schwellwert-Genehmigung",
        "description": "N von M müssen genehmigen (z.B. 2 von 3)",
        "category": "approval",
        "icon": "users",
        "config_schema": {
            "approvers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "uuid", "optional": True},
                        "role": {"type": "string", "optional": True},
                    },
                },
            },
            "required_approvals": {"type": "number", "required": True},
            "timeout_hours": {"type": "number", "default": 48},
        },
        "inputs": ["input"],
        "outputs": ["approved", "rejected", "timeout"],
    },
    # Bedingungs-Blocks
    "condition_amount": {
        "type": BlockType.CONDITION,
        "label": "Betrags-Bedingung",
        "description": "Verzweigung basierend auf Betrag",
        "category": "condition",
        "icon": "git-branch",
        "config_schema": {
            "field": {"type": "string", "default": "amount"},
            "operator": {"type": "string", "enum": ["gt", "lt", "gte", "lte", "eq"]},
            "value": {"type": "number", "required": True},
        },
        "inputs": ["input"],
        "outputs": ["true", "false"],
    },
    "condition_document_type": {
        "type": BlockType.CONDITION,
        "label": "Dokumenttyp-Bedingung",
        "description": "Verzweigung nach Dokumenttyp",
        "category": "condition",
        "icon": "file-question",
        "config_schema": {
            "document_types": {
                "type": "array",
                "items": {"type": "string"},
                "required": True,
            },
        },
        "inputs": ["input"],
        "outputs": ["match", "no_match"],
    },
    "condition_entity": {
        "type": BlockType.CONDITION,
        "label": "Geschäftspartner-Bedingung",
        "description": "Verzweigung nach Geschäftspartner",
        "category": "condition",
        "icon": "building",
        "config_schema": {
            "entity_ids": {"type": "array", "items": {"type": "uuid"}, "optional": True},
            "entity_tags": {"type": "array", "items": {"type": "string"}, "optional": True},
            "risk_score_threshold": {"type": "number", "optional": True},
        },
        "inputs": ["input"],
        "outputs": ["match", "no_match"],
    },
    "condition_custom": {
        "type": BlockType.CONDITION,
        "label": "Benutzerdefinierte Bedingung",
        "description": "Eigene Bedingungslogik",
        "category": "condition",
        "icon": "code",
        "config_schema": {
            "conditions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "field": {"type": "string"},
                        "operator": {"type": "string"},
                        "value": {"type": "any"},
                    },
                },
            },
            "logic": {"type": "string", "enum": ["AND", "OR"], "default": "AND"},
        },
        "inputs": ["input"],
        "outputs": ["true", "false"],
    },
    # Benachrichtigungs-Blocks
    "notification_email": {
        "type": BlockType.NOTIFICATION,
        "label": "E-Mail senden",
        "description": "Sendet E-Mail-Benachrichtigung",
        "category": "notification",
        "icon": "mail",
        "config_schema": {
            "recipients": {"type": "array", "items": {"type": "string"}},
            "subject_template": {"type": "string", "required": True},
            "body_template": {"type": "string", "required": True},
            "include_document": {"type": "boolean", "default": False},
        },
        "inputs": ["input"],
        "outputs": ["sent", "failed"],
    },
    "notification_slack": {
        "type": BlockType.NOTIFICATION,
        "label": "Slack-Nachricht",
        "description": "Sendet Slack-Benachrichtigung",
        "category": "notification",
        "icon": "slack",
        "config_schema": {
            "channel": {"type": "string", "required": True},
            "message_template": {"type": "string", "required": True},
            "mention_users": {"type": "array", "items": {"type": "string"}, "optional": True},
        },
        "inputs": ["input"],
        "outputs": ["sent", "failed"],
    },
    "notification_in_app": {
        "type": BlockType.NOTIFICATION,
        "label": "In-App Benachrichtigung",
        "description": "Erstellt In-App Benachrichtigung",
        "category": "notification",
        "icon": "bell",
        "config_schema": {
            "recipients": {"type": "array", "items": {"type": "uuid"}},
            "title_template": {"type": "string", "required": True},
            "message_template": {"type": "string", "required": True},
            "priority": {"type": "string", "enum": ["low", "medium", "high"], "default": "medium"},
        },
        "inputs": ["input"],
        "outputs": ["next"],
    },
    # Aktions-Blocks
    "action_set_status": {
        "type": BlockType.ACTION,
        "label": "Status setzen",
        "description": "Setzt Dokument-Status",
        "category": "action",
        "icon": "tag",
        "config_schema": {
            "status": {"type": "string", "required": True},
        },
        "inputs": ["input"],
        "outputs": ["next"],
    },
    "action_add_tags": {
        "type": BlockType.ACTION,
        "label": "Tags hinzufuegen",
        "description": "Fuegt Tags zu Dokument hinzu",
        "category": "action",
        "icon": "tags",
        "config_schema": {
            "tags": {"type": "array", "items": {"type": "string"}, "required": True},
        },
        "inputs": ["input"],
        "outputs": ["next"],
    },
    "action_move_folder": {
        "type": BlockType.ACTION,
        "label": "In Ordner verschieben",
        "description": "Verschiebt Dokument in Ordner",
        "category": "action",
        "icon": "folder",
        "config_schema": {
            "folder_id": {"type": "uuid", "required": True},
        },
        "inputs": ["input"],
        "outputs": ["next"],
    },
    "action_trigger_ocr": {
        "type": BlockType.ACTION,
        "label": "OCR starten",
        "description": "Startet OCR-Verarbeitung",
        "category": "action",
        "icon": "scan",
        "config_schema": {
            "backend": {"type": "string", "enum": ["auto", "deepseek", "got_ocr", "surya"], "default": "auto"},
            "force_reprocess": {"type": "boolean", "default": False},
        },
        "inputs": ["input"],
        "outputs": ["success", "failed"],
    },
    "action_create_invoice": {
        "type": BlockType.ACTION,
        "label": "Rechnung erfassen",
        "description": "Erstellt Rechnungs-Eintrag aus Dokument",
        "category": "action",
        "icon": "receipt",
        "config_schema": {
            "auto_link_entity": {"type": "boolean", "default": True},
            "dunning_enabled": {"type": "boolean", "default": True},
        },
        "inputs": ["input"],
        "outputs": ["success", "failed"],
    },
    # Verzögerungs-Blocks
    "delay_fixed": {
        "type": BlockType.DELAY,
        "label": "Feste Verzögerung",
        "description": "Wartet eine feste Zeitspanne",
        "category": "delay",
        "icon": "clock",
        "config_schema": {
            "duration_seconds": {"type": "number", "optional": True},
            "duration_minutes": {"type": "number", "optional": True},
            "duration_hours": {"type": "number", "optional": True},
            "duration_days": {"type": "number", "optional": True},
        },
        "inputs": ["input"],
        "outputs": ["next"],
    },
    "delay_until": {
        "type": BlockType.DELAY,
        "label": "Warten bis",
        "description": "Wartet bis zu einem bestimmten Zeitpunkt",
        "category": "delay",
        "icon": "calendar-clock",
        "config_schema": {
            "until_datetime": {"type": "datetime", "optional": True},
            "until_field": {"type": "string", "optional": True},
            "offset_days": {"type": "number", "default": 0},
        },
        "inputs": ["input"],
        "outputs": ["next"],
    },
    # End-Block
    "end": {
        "type": BlockType.END,
        "label": "Ende",
        "description": "Workflow beenden",
        "category": "control",
        "icon": "flag",
        "config_schema": {
            "final_status": {"type": "string", "optional": True},
        },
        "inputs": ["input"],
        "outputs": [],
    },
}


# =============================================================================
# Visual Workflow Builder Service
# =============================================================================


class VisualWorkflowBuilderService:
    """Service für den visuellen Workflow-Builder.

    Ermöglicht Business-Usern das Erstellen von Workflows per Drag&Drop
    ohne Code-Kenntnisse.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialisiert den Service.

        Args:
            db: AsyncSession für Datenbankoperationen
        """
        self.db = db
        self.workflow_service = WorkflowService(db)

    # =========================================================================
    # Block-Katalog
    # =========================================================================

    def get_available_blocks(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Gibt verfügbare Workflow-Blocks zurück.

        Args:
            category: Optionaler Filter nach Kategorie

        Returns:
            Liste der Block-Definitionen
        """
        blocks = []

        for block_id, definition in BLOCK_DEFINITIONS.items():
            if category and definition.get("category") != category:
                continue

            blocks.append({
                "id": block_id,
                "type": definition["type"].value if isinstance(definition["type"], BlockType) else definition["type"],
                "label": definition["label"],
                "description": definition["description"],
                "category": definition.get("category", "other"),
                "icon": definition.get("icon", "box"),
                "config_schema": definition.get("config_schema", {}),
                "inputs": definition.get("inputs", []),
                "outputs": definition.get("outputs", []),
            })

        return blocks

    def get_block_categories(self) -> List[Dict[str, str]]:
        """Gibt verfügbare Block-Kategorien zurück.

        Returns:
            Liste der Kategorien mit Labels
        """
        return [
            {"id": "trigger", "label": "Trigger", "description": "Workflow-Startbedingungen"},
            {"id": "approval", "label": "Genehmigung", "description": "Genehmigungs-Workflows"},
            {"id": "condition", "label": "Bedingung", "description": "Verzweigungen"},
            {"id": "notification", "label": "Benachrichtigung", "description": "Benachrichtigungen senden"},
            {"id": "action", "label": "Aktion", "description": "Aktionen ausführen"},
            {"id": "delay", "label": "Verzögerung", "description": "Warten"},
            {"id": "control", "label": "Steuerung", "description": "Workflow-Steuerung"},
        ]

    # =========================================================================
    # Workflow-Erstellung aus visuellem Editor
    # =========================================================================

    async def create_workflow_from_visual(
        self,
        user_id: UUID,
        company_id: UUID,
        name: str,
        blocks: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        description: Optional[str] = None,
        variables: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[UUID], List[str]]:
        """Erstellt Workflow aus visueller Definition.

        Args:
            user_id: ID des erstellenden Users
            company_id: Company-ID für Multi-Tenant
            name: Workflow-Name
            blocks: Liste der Block-Definitionen
            edges: Liste der Verbindungen
            description: Optionale Beschreibung
            variables: Optionale Variablen

        Returns:
            Tuple aus (Workflow-ID, Validierungsfehler)
        """
        # 1. Validierung
        validation_errors = self._validate_visual_workflow(blocks, edges)
        if validation_errors:
            return None, validation_errors

        # 2. Trigger extrahieren
        trigger_block = self._find_trigger_block(blocks)
        if not trigger_block:
            return None, ["Kein Trigger-Block gefunden"]

        trigger_type, trigger_config = self._extract_trigger_config(trigger_block)

        # 3. Blocks in ReactFlow-Nodes konvertieren
        nodes = self._blocks_to_reactflow_nodes(blocks)
        reactflow_edges = self._edges_to_reactflow_edges(edges)

        # 4. Workflow erstellen
        workflow = await self.workflow_service.create_workflow(
            user_id=user_id,
            company_id=company_id,
            name=name,
            trigger_type=trigger_type,
            trigger_config=trigger_config,
            nodes=nodes,
            edges=reactflow_edges,
            description=description,
            variables=variables or {},
        )

        # 5. Steps aus Blocks erstellen
        await self._create_steps_from_blocks(workflow.id, blocks, user_id, company_id)

        logger.info(
            "visual_workflow_created",
            workflow_id=str(workflow.id),
            name=name,
            block_count=len(blocks),
            edge_count=len(edges),
        )

        return workflow.id, []

    async def update_workflow_from_visual(
        self,
        workflow_id: UUID,
        user_id: UUID,
        company_id: UUID,
        blocks: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Tuple[bool, List[str]]:
        """Aktualisiert Workflow aus visueller Definition.

        Args:
            workflow_id: Workflow-ID
            user_id: User-ID
            company_id: Company-ID
            blocks: Aktualisierte Block-Definitionen
            edges: Aktualisierte Verbindungen
            name: Optionaler neuer Name
            description: Optionale neue Beschreibung

        Returns:
            Tuple aus (Erfolg, Validierungsfehler)
        """
        # Validierung
        validation_errors = self._validate_visual_workflow(blocks, edges)
        if validation_errors:
            return False, validation_errors

        # Trigger extrahieren
        trigger_block = self._find_trigger_block(blocks)
        if not trigger_block:
            return False, ["Kein Trigger-Block gefunden"]

        trigger_type, trigger_config = self._extract_trigger_config(trigger_block)

        # Konvertierung
        nodes = self._blocks_to_reactflow_nodes(blocks)
        reactflow_edges = self._edges_to_reactflow_edges(edges)

        # Update
        updates: Dict[str, Any] = {
            "trigger_type": trigger_type,
            "trigger_config": trigger_config,
            "nodes": nodes,
            "edges": reactflow_edges,
        }

        if name:
            updates["name"] = name
        if description:
            updates["description"] = description

        workflow = await self.workflow_service.update_workflow(
            workflow_id=workflow_id,
            user_id=user_id,
            company_id=company_id,
            **updates,
        )

        if not workflow:
            return False, ["Workflow nicht gefunden oder keine Berechtigung"]

        # Steps neu erstellen
        from sqlalchemy import delete
        from app.db.models import WorkflowStep

        await self.db.execute(
            delete(WorkflowStep).where(WorkflowStep.workflow_id == workflow_id)
        )
        await self._create_steps_from_blocks(workflow_id, blocks, user_id, company_id)

        logger.info(
            "visual_workflow_updated",
            workflow_id=str(workflow_id),
            block_count=len(blocks),
        )

        return True, []

    # =========================================================================
    # Workflow-Simulation (Dry-Run)
    # =========================================================================

    async def simulate_workflow(
        self,
        blocks: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        test_data: Dict[str, Any],
    ) -> SimulationResult:
        """Simuliert Workflow-Ausführung.

        Args:
            blocks: Block-Definitionen
            edges: Verbindungen
            test_data: Testdaten für Simulation

        Returns:
            SimulationResult mit Ausführungspfad
        """
        execution_path: List[str] = []
        outputs: Dict[str, Any] = {}
        warnings: List[str] = []
        errors: List[str] = []
        duration_estimate = 0

        # Validierung
        validation_errors = self._validate_visual_workflow(blocks, edges)
        if validation_errors:
            return SimulationResult(
                success=False,
                execution_path=[],
                simulated_outputs={},
                warnings=[],
                errors=validation_errors,
                duration_estimate_seconds=0,
            )

        # Trigger finden
        trigger_block = self._find_trigger_block(blocks)
        if not trigger_block:
            return SimulationResult(
                success=False,
                execution_path=[],
                simulated_outputs={},
                warnings=[],
                errors=["Kein Trigger-Block gefunden"],
                duration_estimate_seconds=0,
            )

        # Adjacency-Liste erstellen
        adjacency = self._build_adjacency_list(edges)
        block_map = {b["id"]: b for b in blocks}

        # Simulation starten
        current_id = trigger_block["id"]
        visited = set()
        max_iterations = 100  # Schutz vor Endlosschleifen

        while current_id and len(visited) < max_iterations:
            if current_id in visited:
                warnings.append(f"Zyklus erkannt bei Block {current_id}")
                break

            visited.add(current_id)
            block = block_map.get(current_id)

            if not block:
                errors.append(f"Block nicht gefunden: {current_id}")
                break

            execution_path.append(current_id)

            # Block-spezifische Simulation
            block_type = block.get("type", "")
            config = block.get("config", {})

            if block_type == BlockType.END.value or block_type == "end":
                # Ende erreicht
                break

            elif block_type == BlockType.DELAY.value or block_type == "delay":
                # Verzögerung berechnen
                delay_seconds = self._calculate_delay_seconds(config)
                duration_estimate += delay_seconds
                outputs[current_id] = {"delayed_seconds": delay_seconds}

            elif block_type == BlockType.APPROVAL.value or block_type == "approval":
                # Genehmigung simulieren (immer genehmigt)
                timeout_hours = config.get("timeout_hours", 48)
                duration_estimate += timeout_hours * 3600 // 2  # Durchschnittlich halbe Zeit
                outputs[current_id] = {"simulated_result": "approved"}
                warnings.append(f"Block {current_id}: Genehmigung wird als 'genehmigt' simuliert")

            elif block_type == BlockType.CONDITION.value or block_type == "condition":
                # Bedingung auswerten
                condition_result = self._evaluate_condition(config, test_data)
                outputs[current_id] = {"condition_result": condition_result}

            elif block_type == BlockType.NOTIFICATION.value or block_type == "notification":
                outputs[current_id] = {"simulated_sent": True}

            elif block_type == BlockType.ACTION.value or block_type == "action":
                outputs[current_id] = {"simulated_executed": True}

            # Nächsten Block finden
            next_blocks = adjacency.get(current_id, [])

            if not next_blocks:
                break
            elif len(next_blocks) == 1:
                current_id = next_blocks[0]
            else:
                # Mehrere Ausgaenge - basierend auf Bedingungsergebnis wählen
                if block_type in [BlockType.CONDITION.value, "condition"]:
                    # Bei Bedingung: "true" oder "match" Pfad wählen basierend auf Ergebnis
                    condition_result = outputs.get(current_id, {}).get("condition_result", True)
                    # Finde passende Edge
                    for edge in edges:
                        if edge.get("source_id") == current_id:
                            handle = edge.get("source_handle", "")
                            if (condition_result and handle in ["true", "match"]) or \
                               (not condition_result and handle in ["false", "no_match"]):
                                current_id = edge.get("target_id")
                                break
                    else:
                        current_id = next_blocks[0]
                elif block_type in [BlockType.APPROVAL.value, "approval"]:
                    # Bei Genehmigung: "approved" Pfad wählen
                    for edge in edges:
                        if edge.get("source_id") == current_id and edge.get("source_handle") == "approved":
                            current_id = edge.get("target_id")
                            break
                    else:
                        current_id = next_blocks[0]
                else:
                    current_id = next_blocks[0]

        return SimulationResult(
            success=len(errors) == 0,
            execution_path=execution_path,
            simulated_outputs=outputs,
            warnings=warnings,
            errors=errors,
            duration_estimate_seconds=duration_estimate,
        )

    # =========================================================================
    # Template-Funktionen
    # =========================================================================

    def get_workflow_templates(self) -> List[Dict[str, Any]]:
        """Gibt vordefinierte Workflow-Templates zurück.

        Returns:
            Liste der Template-Definitionen
        """
        return [
            {
                "id": "invoice_approval_simple",
                "name": "Einfache Rechnungsgenehmigung",
                "description": "Rechnung ab 1000 EUR benötigt Genehmigung",
                "category": "approval",
                "blocks": [
                    {
                        "id": "trigger",
                        "type": "trigger_invoice_received",
                        "config": {},
                        "position_x": 100,
                        "position_y": 100,
                    },
                    {
                        "id": "condition_amount",
                        "type": "condition_amount",
                        "config": {"operator": "gte", "value": 1000},
                        "position_x": 300,
                        "position_y": 100,
                    },
                    {
                        "id": "approval",
                        "type": "approval_single",
                        "config": {"approver_role": "manager", "timeout_hours": 48},
                        "position_x": 500,
                        "position_y": 50,
                    },
                    {
                        "id": "notify_approved",
                        "type": "notification_email",
                        "config": {
                            "subject_template": "Rechnung genehmigt: {{document.title}}",
                            "body_template": "Die Rechnung wurde genehmigt.",
                        },
                        "position_x": 700,
                        "position_y": 50,
                    },
                    {
                        "id": "auto_approve",
                        "type": "action_set_status",
                        "config": {"status": "approved"},
                        "position_x": 500,
                        "position_y": 150,
                    },
                    {
                        "id": "end",
                        "type": "end",
                        "config": {},
                        "position_x": 900,
                        "position_y": 100,
                    },
                ],
                "edges": [
                    {"source_id": "trigger", "target_id": "condition_amount"},
                    {"source_id": "condition_amount", "target_id": "approval", "source_handle": "true"},
                    {"source_id": "condition_amount", "target_id": "auto_approve", "source_handle": "false"},
                    {"source_id": "approval", "target_id": "notify_approved", "source_handle": "approved"},
                    {"source_id": "notify_approved", "target_id": "end"},
                    {"source_id": "auto_approve", "target_id": "end"},
                ],
            },
            {
                "id": "invoice_approval_multi",
                "name": "Multi-Level Rechnungsgenehmigung",
                "description": "Gestaffelte Genehmigung nach Betrag",
                "category": "approval",
                "blocks": [
                    {
                        "id": "trigger",
                        "type": "trigger_invoice_received",
                        "config": {},
                        "position_x": 100,
                        "position_y": 150,
                    },
                    {
                        "id": "check_5000",
                        "type": "condition_amount",
                        "config": {"operator": "gte", "value": 5000},
                        "position_x": 300,
                        "position_y": 150,
                    },
                    {
                        "id": "check_1000",
                        "type": "condition_amount",
                        "config": {"operator": "gte", "value": 1000},
                        "position_x": 500,
                        "position_y": 200,
                    },
                    {
                        "id": "approval_director",
                        "type": "approval_single",
                        "config": {"approver_role": "director", "timeout_hours": 24},
                        "position_x": 500,
                        "position_y": 50,
                    },
                    {
                        "id": "approval_manager",
                        "type": "approval_single",
                        "config": {"approver_role": "manager", "timeout_hours": 48},
                        "position_x": 700,
                        "position_y": 150,
                    },
                    {
                        "id": "auto_approve",
                        "type": "action_set_status",
                        "config": {"status": "approved"},
                        "position_x": 700,
                        "position_y": 250,
                    },
                    {
                        "id": "end",
                        "type": "end",
                        "config": {},
                        "position_x": 900,
                        "position_y": 150,
                    },
                ],
                "edges": [
                    {"source_id": "trigger", "target_id": "check_5000"},
                    {"source_id": "check_5000", "target_id": "approval_director", "source_handle": "true"},
                    {"source_id": "check_5000", "target_id": "check_1000", "source_handle": "false"},
                    {"source_id": "approval_director", "target_id": "approval_manager", "source_handle": "approved"},
                    {"source_id": "check_1000", "target_id": "approval_manager", "source_handle": "true"},
                    {"source_id": "check_1000", "target_id": "auto_approve", "source_handle": "false"},
                    {"source_id": "approval_manager", "target_id": "end", "source_handle": "approved"},
                    {"source_id": "auto_approve", "target_id": "end"},
                ],
            },
            {
                "id": "document_processing",
                "name": "Dokumenten-Verarbeitung",
                "description": "Automatische OCR und Kategorisierung",
                "category": "automation",
                "blocks": [
                    {
                        "id": "trigger",
                        "type": "trigger_document_upload",
                        "config": {},
                        "position_x": 100,
                        "position_y": 100,
                    },
                    {
                        "id": "ocr",
                        "type": "action_trigger_ocr",
                        "config": {"backend": "auto"},
                        "position_x": 300,
                        "position_y": 100,
                    },
                    {
                        "id": "check_invoice",
                        "type": "condition_document_type",
                        "config": {"document_types": ["invoice", "rechnung"]},
                        "position_x": 500,
                        "position_y": 100,
                    },
                    {
                        "id": "create_invoice",
                        "type": "action_create_invoice",
                        "config": {"auto_link_entity": True},
                        "position_x": 700,
                        "position_y": 50,
                    },
                    {
                        "id": "add_tags",
                        "type": "action_add_tags",
                        "config": {"tags": ["automatisch_verarbeitet"]},
                        "position_x": 700,
                        "position_y": 150,
                    },
                    {
                        "id": "end",
                        "type": "end",
                        "config": {},
                        "position_x": 900,
                        "position_y": 100,
                    },
                ],
                "edges": [
                    {"source_id": "trigger", "target_id": "ocr"},
                    {"source_id": "ocr", "target_id": "check_invoice", "source_handle": "success"},
                    {"source_id": "check_invoice", "target_id": "create_invoice", "source_handle": "match"},
                    {"source_id": "check_invoice", "target_id": "add_tags", "source_handle": "no_match"},
                    {"source_id": "create_invoice", "target_id": "end", "source_handle": "success"},
                    {"source_id": "add_tags", "target_id": "end"},
                ],
            },
            {
                "id": "payment_reminder",
                "name": "Zahlungserinnerung",
                "description": "Automatische Mahnung bei überfälliger Zahlung",
                "category": "reminder",
                "blocks": [
                    {
                        "id": "trigger",
                        "type": "trigger_schedule",
                        "config": {"cron": "0 9 * * *"},  # Täglich um 9 Uhr
                        "position_x": 100,
                        "position_y": 100,
                    },
                    {
                        "id": "check_overdue",
                        "type": "condition_custom",
                        "config": {
                            "conditions": [
                                {"field": "invoice.is_overdue", "operator": "equals", "value": True}
                            ]
                        },
                        "position_x": 300,
                        "position_y": 100,
                    },
                    {
                        "id": "send_reminder",
                        "type": "notification_email",
                        "config": {
                            "subject_template": "Zahlungserinnerung: Rechnung {{invoice.number}}",
                            "body_template": "Bitte begleichen Sie die offene Rechnung.",
                        },
                        "position_x": 500,
                        "position_y": 50,
                    },
                    {
                        "id": "end",
                        "type": "end",
                        "config": {},
                        "position_x": 700,
                        "position_y": 100,
                    },
                ],
                "edges": [
                    {"source_id": "trigger", "target_id": "check_overdue"},
                    {"source_id": "check_overdue", "target_id": "send_reminder", "source_handle": "true"},
                    {"source_id": "check_overdue", "target_id": "end", "source_handle": "false"},
                    {"source_id": "send_reminder", "target_id": "end", "source_handle": "sent"},
                ],
            },
        ]

    # =========================================================================
    # Private Helper Methods
    # =========================================================================

    def _validate_visual_workflow(
        self,
        blocks: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
    ) -> List[str]:
        """Validiert eine visuelle Workflow-Definition.

        Args:
            blocks: Liste der Blocks
            edges: Liste der Verbindungen

        Returns:
            Liste der Validierungsfehler
        """
        errors: List[str] = []

        if not blocks:
            errors.append("Mindestens ein Block erforderlich")
            return errors

        # Block-IDs sammeln
        block_ids = {b.get("id") for b in blocks if b.get("id")}

        # Trigger-Block prüfen
        trigger_blocks = [b for b in blocks if b.get("type", "").startswith("trigger")]
        if len(trigger_blocks) == 0:
            errors.append("Genau ein Trigger-Block erforderlich")
        elif len(trigger_blocks) > 1:
            errors.append("Nur ein Trigger-Block erlaubt")

        # End-Block prüfen
        end_blocks = [b for b in blocks if b.get("type") == "end"]
        if not end_blocks:
            errors.append("Mindestens ein End-Block erforderlich")

        # Kanten validieren
        for edge in edges:
            source_id = edge.get("source_id")
            target_id = edge.get("target_id")

            if source_id not in block_ids:
                errors.append(f"Unbekannter Quell-Block: {source_id}")
            if target_id not in block_ids:
                errors.append(f"Unbekannter Ziel-Block: {target_id}")

        # Zyklus-Erkennung (vereinfacht)
        adjacency = self._build_adjacency_list(edges)
        if self._has_cycle(adjacency, block_ids):
            errors.append("Zyklus im Workflow erkannt")

        return errors

    def _build_adjacency_list(self, edges: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        """Erstellt Adjacency-Liste aus Kanten.

        Args:
            edges: Liste der Kanten

        Returns:
            Adjacency-Liste
        """
        adjacency: Dict[str, List[str]] = {}

        for edge in edges:
            source = edge.get("source_id")
            target = edge.get("target_id")

            if source and target:
                if source not in adjacency:
                    adjacency[source] = []
                adjacency[source].append(target)

        return adjacency

    def _has_cycle(self, adjacency: Dict[str, List[str]], all_nodes: set) -> bool:
        """Prüft auf Zyklen mittels DFS.

        Args:
            adjacency: Adjacency-Liste
            all_nodes: Alle Knoten-IDs

        Returns:
            True wenn Zyklus gefunden
        """
        UNVISITED, VISITING, VISITED = 0, 1, 2
        state = {node: UNVISITED for node in all_nodes}

        def dfs(node: str) -> bool:
            if state.get(node) == VISITING:
                return True
            if state.get(node) == VISITED:
                return False

            state[node] = VISITING

            for neighbor in adjacency.get(node, []):
                if dfs(neighbor):
                    return True

            state[node] = VISITED
            return False

        for node in all_nodes:
            if state.get(node) == UNVISITED:
                if dfs(node):
                    return True

        return False

    def _find_trigger_block(self, blocks: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Findet den Trigger-Block.

        Args:
            blocks: Liste der Blocks

        Returns:
            Trigger-Block oder None
        """
        for block in blocks:
            if block.get("type", "").startswith("trigger"):
                return block
        return None

    def _extract_trigger_config(
        self, trigger_block: Dict[str, Any]
    ) -> Tuple[str, Dict[str, Any]]:
        """Extrahiert Trigger-Konfiguration.

        Args:
            trigger_block: Trigger-Block

        Returns:
            Tuple aus (trigger_type, trigger_config)
        """
        block_type = trigger_block.get("type", "")
        config = trigger_block.get("config", {})

        type_mapping = {
            "trigger_document_upload": ("document_event", {"events": ["document.uploaded"]}),
            "trigger_invoice_received": ("document_event", {"events": ["invoice.received"]}),
            "trigger_schedule": ("schedule", {"cron": config.get("cron", "0 * * * *")}),
            "trigger_manual": ("manual", {}),
        }

        base_type, base_config = type_mapping.get(block_type, ("manual", {}))

        # Config zusammenführen
        merged_config = {**base_config, **config}

        return base_type, merged_config

    def _blocks_to_reactflow_nodes(
        self, blocks: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Konvertiert Blocks zu ReactFlow-Nodes.

        Args:
            blocks: Liste der Blocks

        Returns:
            ReactFlow-kompatible Node-Liste
        """
        nodes = []

        for block in blocks:
            node = {
                "id": block.get("id"),
                "type": self._get_reactflow_node_type(block.get("type", "")),
                "position": {
                    "x": block.get("position_x", 0),
                    "y": block.get("position_y", 0),
                },
                "data": {
                    "label": block.get("label", block.get("type", "")),
                    "blockType": block.get("type"),
                    "config": block.get("config", {}),
                },
            }
            nodes.append(node)

        return nodes

    def _edges_to_reactflow_edges(
        self, edges: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Konvertiert Edges zu ReactFlow-Edges.

        Args:
            edges: Liste der Edges

        Returns:
            ReactFlow-kompatible Edge-Liste
        """
        reactflow_edges = []

        for edge in edges:
            rf_edge = {
                "id": edge.get("id", f"{edge.get('source_id')}-{edge.get('target_id')}"),
                "source": edge.get("source_id"),
                "target": edge.get("target_id"),
            }

            if edge.get("source_handle"):
                rf_edge["sourceHandle"] = edge.get("source_handle")
            if edge.get("target_handle"):
                rf_edge["targetHandle"] = edge.get("target_handle")
            if edge.get("label"):
                rf_edge["label"] = edge.get("label")

            reactflow_edges.append(rf_edge)

        return reactflow_edges

    def _get_reactflow_node_type(self, block_type: str) -> str:
        """Mappt Block-Typ zu ReactFlow-Node-Typ.

        Args:
            block_type: Block-Typ-String

        Returns:
            ReactFlow Node-Typ
        """
        if block_type.startswith("trigger"):
            return "trigger"
        elif block_type.startswith("approval"):
            return "approval"
        elif block_type.startswith("condition"):
            return "condition"
        elif block_type.startswith("notification"):
            return "notification"
        elif block_type.startswith("action"):
            return "action"
        elif block_type.startswith("delay"):
            return "delay"
        elif block_type == "end":
            return "end"
        else:
            return "default"

    async def _create_steps_from_blocks(
        self,
        workflow_id: UUID,
        blocks: List[Dict[str, Any]],
        user_id: UUID,
        company_id: UUID,
    ) -> None:
        """Erstellt WorkflowSteps aus Blocks.

        Args:
            workflow_id: Workflow-ID
            blocks: Block-Definitionen
            user_id: User-ID
            company_id: Company-ID
        """
        for order, block in enumerate(blocks):
            block_type = block.get("type", "")

            # Trigger-Blocks überspringen (sind in Workflow-Config)
            if block_type.startswith("trigger"):
                continue

            step_type = self._map_block_to_step_type(block_type)

            await self.workflow_service.create_step(
                workflow_id=workflow_id,
                step_order=order,
                step_type=step_type,
                user_id=user_id,
                company_id=company_id,
                step_name=block.get("label", block_type),
                config={
                    "block_type": block_type,
                    **block.get("config", {}),
                },
                position_x=block.get("position_x", 0),
                position_y=block.get("position_y", 0),
            )

    def _map_block_to_step_type(self, block_type: str) -> str:
        """Mappt Block-Typ zu Step-Typ.

        Args:
            block_type: Block-Typ

        Returns:
            Step-Typ
        """
        if block_type.startswith("approval"):
            return "action"  # Approvals werden als Actions mit speziellem Config behandelt
        elif block_type.startswith("condition"):
            return "condition"
        elif block_type.startswith("notification"):
            return "action"
        elif block_type.startswith("action"):
            return "action"
        elif block_type.startswith("delay"):
            return "delay"
        else:
            return "action"

    def _calculate_delay_seconds(self, config: Dict[str, Any]) -> int:
        """Berechnet Verzögerung in Sekunden.

        Args:
            config: Delay-Konfiguration

        Returns:
            Sekunden
        """
        seconds = config.get("duration_seconds", 0)
        seconds += config.get("duration_minutes", 0) * 60
        seconds += config.get("duration_hours", 0) * 3600
        seconds += config.get("duration_days", 0) * 86400

        return seconds

    def _evaluate_condition(
        self, config: Dict[str, Any], test_data: Dict[str, Any]
    ) -> bool:
        """Wertet Bedingung gegen Testdaten aus.

        Args:
            config: Bedingungs-Konfiguration
            test_data: Testdaten

        Returns:
            Bedingungsergebnis
        """
        field = config.get("field", "")
        operator = config.get("operator", "equals")
        value = config.get("value")

        # Feldwert aus Testdaten holen
        actual_value = test_data.get(field)

        # Nested field support (z.B. "document.amount")
        if "." in field:
            parts = field.split(".")
            actual_value = test_data
            for part in parts:
                if isinstance(actual_value, dict):
                    actual_value = actual_value.get(part)
                else:
                    actual_value = None
                    break

        # Operator anwenden
        if operator in ["gt", "greater_than"]:
            return actual_value is not None and actual_value > value
        elif operator in ["lt", "less_than"]:
            return actual_value is not None and actual_value < value
        elif operator in ["gte", "greater_or_equal"]:
            return actual_value is not None and actual_value >= value
        elif operator in ["lte", "less_or_equal"]:
            return actual_value is not None and actual_value <= value
        elif operator in ["eq", "equals"]:
            return actual_value == value
        elif operator in ["neq", "not_equals"]:
            return actual_value != value
        elif operator == "contains":
            return value in str(actual_value) if actual_value else False
        else:
            return True
