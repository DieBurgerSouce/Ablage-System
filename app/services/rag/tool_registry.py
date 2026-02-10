"""Tool-Calling Registry fuer RAG Agent Mode.

Definiert verfuegbare Tools die der LLM aufrufen kann.
Bruecke zwischen LLM-Output und AIActionService.
"""

import re
import json
from typing import List, Optional, Dict
from dataclasses import dataclass
from enum import Enum

import structlog

logger = structlog.get_logger(__name__)


# =============================================================================
# TOOL DEFINITIONS
# =============================================================================

class ToolParameterType(str, Enum):
    """Parameter-Typen fuer Tool-Definitionen."""
    STRING = "string"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"


@dataclass
class ToolParameter:
    """Tool-Parameter Definition."""
    name: str
    type: ToolParameterType
    description: str
    required: bool = False
    items_type: Optional[str] = None  # Fuer arrays


@dataclass
class ToolDefinition:
    """Definition eines aufrufbaren Tools."""
    name: str
    description: str
    parameters: List[ToolParameter]
    requires_confirmation: bool
    permission_level: str  # viewer, editor, admin

    def to_json_schema(self) -> Dict[str, object]:
        """Konvertiert zu JSON Schema fuer LLM."""
        properties = {}
        required = []

        for param in self.parameters:
            param_schema: Dict[str, object] = {
                "type": param.type.value,
                "description": param.description
            }

            if param.type == ToolParameterType.ARRAY and param.items_type:
                param_schema["items"] = {"type": param.items_type}

            properties[param.name] = param_schema

            if param.required:
                required.append(param.name)

        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required
            },
            "requires_confirmation": self.requires_confirmation
        }


# =============================================================================
# TOOL REGISTRY
# =============================================================================

# Alle verfuegbaren Tools
ALL_TOOLS: List[ToolDefinition] = [
    # Read-Only Tools (Viewer+)
    ToolDefinition(
        name="search_documents",
        description="Durchsucht alle Dokumente nach bestimmten Kriterien. Findet Rechnungen, Vertraege, Lieferscheine etc.",
        parameters=[
            ToolParameter("query", ToolParameterType.STRING, "Suchbegriff oder Beschreibung", required=True),
            ToolParameter("document_type", ToolParameterType.STRING, "Filter nach Dokumenttyp (z.B. 'Rechnung', 'Vertrag')"),
            ToolParameter("date_from", ToolParameterType.STRING, "Start-Datum im Format YYYY-MM-DD"),
            ToolParameter("date_to", ToolParameterType.STRING, "End-Datum im Format YYYY-MM-DD"),
        ],
        requires_confirmation=False,
        permission_level="viewer"
    ),

    ToolDefinition(
        name="get_invoice_status",
        description="Ruft den Status von Rechnungen eines Geschaeftspartners ab (offen, bezahlt, ueberfaellig).",
        parameters=[
            ToolParameter("entity_name", ToolParameterType.STRING, "Name des Kunden oder Lieferanten", required=True),
        ],
        requires_confirmation=False,
        permission_level="viewer"
    ),

    ToolDefinition(
        name="filter_documents",
        description="Filtert Dokumente nach Typ, Zeitraum oder Status.",
        parameters=[
            ToolParameter("document_type", ToolParameterType.STRING, "Dokumenttyp (z.B. 'Rechnung', 'Lieferschein')", required=True),
            ToolParameter("date_range", ToolParameterType.STRING, "Zeitraum (z.B. 'letzter_monat', 'dieses_jahr')"),
            ToolParameter("status", ToolParameterType.STRING, "Status-Filter (z.B. 'offen', 'bezahlt')"),
        ],
        requires_confirmation=False,
        permission_level="viewer"
    ),

    ToolDefinition(
        name="get_entity_summary",
        description="Erstellt eine Zusammenfassung zu einem Geschaeftspartner (Umsatz, offene Posten, Zahlungsverhalten).",
        parameters=[
            ToolParameter("entity_name", ToolParameterType.STRING, "Name des Kunden oder Lieferanten", required=True),
        ],
        requires_confirmation=False,
        permission_level="viewer"
    ),

    # Write Tools (Editor+ mit Bestaetigung)
    ToolDefinition(
        name="move_document",
        description="Verschiebt ein Dokument in einen anderen Ordner.",
        parameters=[
            ToolParameter("document_id", ToolParameterType.STRING, "UUID des Dokuments", required=True),
            ToolParameter("folder_id", ToolParameterType.STRING, "UUID des Ziel-Ordners", required=True),
        ],
        requires_confirmation=True,
        permission_level="admin"
    ),

    ToolDefinition(
        name="tag_document",
        description="Fuegt Tags zu einem Dokument hinzu.",
        parameters=[
            ToolParameter("document_id", ToolParameterType.STRING, "UUID des Dokuments", required=True),
            ToolParameter("tags", ToolParameterType.ARRAY, "Liste von Tags", required=True, items_type="string"),
        ],
        requires_confirmation=True,
        permission_level="editor"
    ),

    ToolDefinition(
        name="categorize_document",
        description="Ordnet ein Dokument einer Kategorie zu (z.B. 'Rechnung', 'Vertrag').",
        parameters=[
            ToolParameter("document_id", ToolParameterType.STRING, "UUID des Dokuments", required=True),
            ToolParameter("category", ToolParameterType.STRING, "Kategorie-Name", required=True),
        ],
        requires_confirmation=True,
        permission_level="editor"
    ),

    ToolDefinition(
        name="create_reminder",
        description="Erstellt eine Erinnerung zu einem Dokument oder einer Aufgabe.",
        parameters=[
            ToolParameter("title", ToolParameterType.STRING, "Titel der Erinnerung", required=True),
            ToolParameter("due_date", ToolParameterType.STRING, "Faelligkeitsdatum im Format YYYY-MM-DD", required=True),
            ToolParameter("document_id", ToolParameterType.STRING, "Optional: Verknuepfte Dokument-UUID"),
        ],
        requires_confirmation=True,
        permission_level="editor"
    ),
]


class ToolRegistry:
    """Registry fuer verfuegbare Tools."""

    def __init__(self) -> None:
        """Initialisiert die Tool Registry."""
        self._tools = {tool.name: tool for tool in ALL_TOOLS}

    def get_tools_for_user(self, user_level: str) -> List[ToolDefinition]:
        """Gibt verfuegbare Tools basierend auf User-Level zurueck.

        Args:
            user_level: viewer, editor, oder admin

        Returns:
            Liste verfuegbarer Tools
        """
        level_hierarchy = {
            "viewer": ["viewer"],
            "editor": ["viewer", "editor"],
            "admin": ["viewer", "editor", "admin"]
        }

        allowed_levels = level_hierarchy.get(user_level, ["viewer"])

        return [
            tool for tool in ALL_TOOLS
            if tool.permission_level in allowed_levels
        ]

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """Gibt ein Tool nach Namen zurueck.

        Args:
            name: Tool-Name

        Returns:
            ToolDefinition oder None
        """
        return self._tools.get(name)

    def format_tools_for_llm(self, user_level: str = "viewer") -> str:
        """Formatiert Tool-Liste als Text fuer LLM System-Prompt.

        Args:
            user_level: viewer, editor, oder admin

        Returns:
            Formatierter Tool-Text
        """
        tools = self.get_tools_for_user(user_level)

        if not tools:
            return "Keine Tools verfuegbar."

        lines = ["VERFUEGBARE TOOLS:", ""]

        for tool in tools:
            lines.append(f"**{tool.name}**")
            lines.append(f"Beschreibung: {tool.description}")
            lines.append("Parameter:")

            for param in tool.parameters:
                required = " (erforderlich)" if param.required else " (optional)"
                lines.append(f"  - {param.name} ({param.type.value}){required}: {param.description}")

            if tool.requires_confirmation:
                lines.append("⚠️  Bestaetigung erforderlich vor Ausfuehrung")

            lines.append("")

        lines.append("FORMAT ZUM AUFRUFEN:")
        lines.append('<tool_call>{"tool": "tool_name", "params": {"param1": "value1"}}</tool_call>')
        lines.append("")

        return "\n".join(lines)

    def parse_tool_call(self, llm_output: str) -> Optional['ToolCall']:
        """Parst Tool-Call aus LLM-Output.

        Sucht nach <tool_call>...</tool_call> Bloecken.

        Args:
            llm_output: Vollstaendige LLM-Antwort

        Returns:
            ToolCall oder None wenn kein Tool-Call gefunden
        """
        # Suche nach <tool_call>...</tool_call>
        pattern = r'<tool_call>\s*(.*?)\s*</tool_call>'
        matches = re.finditer(pattern, llm_output, re.DOTALL)

        tool_calls: List[ToolCall] = []

        for match in matches:
            try:
                json_str = match.group(1)
                data = json.loads(json_str)

                tool_name = data.get("tool")
                params = data.get("params", {})

                if not tool_name:
                    logger.warning("tool_call_missing_name", json_data=data)
                    continue

                # Tool existiert?
                tool = self.get_tool(tool_name)
                if not tool:
                    logger.warning("tool_call_unknown_tool", tool_name=tool_name)
                    continue

                tool_calls.append(ToolCall(
                    tool_name=tool_name,
                    parameters=params
                ))

            except json.JSONDecodeError as e:
                logger.warning("tool_call_json_parse_failed", error=str(e), json_str=match.group(1))
                continue

        # Gib ersten Tool-Call zurueck (Multi-Call TODO)
        return tool_calls[0] if tool_calls else None


@dataclass
class ToolCall:
    """Geparster Tool-Call aus LLM-Output."""
    tool_name: str
    parameters: Dict[str, object]


# =============================================================================
# SINGLETON
# =============================================================================

_tool_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """Gibt Tool Registry Singleton zurueck.

    Returns:
        ToolRegistry Instanz
    """
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = ToolRegistry()
    return _tool_registry
