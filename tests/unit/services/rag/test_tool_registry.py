# -*- coding: utf-8 -*-
"""Tests fuer RAG Agent Tool Registry.

Testet Tool-Definitionen, Permission-Filtering und LLM-Output-Parsing.
"""

import pytest
from typing import List, Dict

from app.services.rag.tool_registry import (
    ToolRegistry,
    ToolDefinition,
    ToolCall,
    ToolParameterType,
    get_tool_registry,
)

# Test markers
pytestmark = [pytest.mark.unit, pytest.mark.services]


class TestToolRegistry:
    """Tests fuer ToolRegistry."""

    def test_registry_has_all_tools(self) -> None:
        """Alle 8 Tools sind registriert."""
        registry = ToolRegistry()

        # Alle Tools abrufen (admin = all tools)
        all_tools = registry.get_tools_for_user("admin")

        assert len(all_tools) == 8, "Registry muss genau 8 Tools enthalten"

        tool_names = {tool.name for tool in all_tools}
        expected_names = {
            "search_documents",
            "get_invoice_status",
            "filter_documents",
            "get_entity_summary",
            "move_document",
            "tag_document",
            "categorize_document",
            "create_reminder",
        }

        assert tool_names == expected_names, "Alle erwarteten Tools muessen vorhanden sein"

    def test_get_tool_by_name(self) -> None:
        """Kann spezifisches Tool abrufen."""
        registry = ToolRegistry()

        tool = registry.get_tool("search_documents")

        assert tool is not None, "Tool sollte gefunden werden"
        assert tool.name == "search_documents"
        assert tool.permission_level == "viewer"
        assert tool.requires_confirmation is False

    def test_get_tool_unknown_returns_none(self) -> None:
        """Unbekanntes Tool gibt None zurueck."""
        registry = ToolRegistry()

        tool = registry.get_tool("unknown_tool_xyz")

        assert tool is None, "Unbekanntes Tool sollte None zurueckgeben"

    def test_viewer_tools(self) -> None:
        """Viewer bekommt nur read-only Tools."""
        registry = ToolRegistry()

        viewer_tools = registry.get_tools_for_user("viewer")

        assert len(viewer_tools) == 4, "Viewer sollte 4 Tools haben"

        tool_names = {tool.name for tool in viewer_tools}
        expected_names = {
            "search_documents",
            "get_invoice_status",
            "filter_documents",
            "get_entity_summary",
        }

        assert tool_names == expected_names, "Viewer sollte nur read-only Tools haben"

        # Alle Viewer-Tools sollten keine Bestaetigung benoetigen
        for tool in viewer_tools:
            assert tool.requires_confirmation is False, f"Tool {tool.name} sollte keine Bestaetigung brauchen"

    def test_editor_tools(self) -> None:
        """Editor bekommt viewer tools + write tools."""
        registry = ToolRegistry()

        editor_tools = registry.get_tools_for_user("editor")

        assert len(editor_tools) == 7, "Editor sollte 7 Tools haben"

        tool_names = {tool.name for tool in editor_tools}
        expected_names = {
            "search_documents",
            "get_invoice_status",
            "filter_documents",
            "get_entity_summary",
            "tag_document",
            "categorize_document",
            "create_reminder",
        }

        assert tool_names == expected_names, "Editor sollte viewer + write tools haben"

    def test_admin_tools(self) -> None:
        """Admin bekommt alle Tools inkl move_document."""
        registry = ToolRegistry()

        admin_tools = registry.get_tools_for_user("admin")

        assert len(admin_tools) == 8, "Admin sollte alle 8 Tools haben"

        tool_names = {tool.name for tool in admin_tools}
        assert "move_document" in tool_names, "Admin sollte move_document haben"

    def test_format_tools_for_llm(self) -> None:
        """Output enthaelt Tool-Namen und Beschreibungen."""
        registry = ToolRegistry()

        formatted = registry.format_tools_for_llm("viewer")

        assert "VERFUEGBARE TOOLS:" in formatted
        assert "search_documents" in formatted
        assert "Durchsucht alle Dokumente" in formatted
        assert "FORMAT ZUM AUFRUFEN:" in formatted
        assert '<tool_call>{"tool": "tool_name", "params": {"param1": "value1"}}</tool_call>' in formatted

    def test_parse_tool_call_valid(self) -> None:
        """Parst validen Tool-Call."""
        registry = ToolRegistry()

        llm_output = '''
        Ich suche nach Dokumenten.
        <tool_call>{"tool": "search_documents", "params": {"query": "test"}}</tool_call>
        Das sind die Ergebnisse.
        '''

        tool_call = registry.parse_tool_call(llm_output)

        assert tool_call is not None, "Tool-Call sollte geparst werden"
        assert tool_call.tool_name == "search_documents"
        assert tool_call.parameters == {"query": "test"}

    def test_parse_tool_call_no_block(self) -> None:
        """Regulaerer Text ohne Tool-Call gibt None."""
        registry = ToolRegistry()

        llm_output = "Dies ist nur normaler Text ohne Tool-Call."

        tool_call = registry.parse_tool_call(llm_output)

        assert tool_call is None, "Kein Tool-Call sollte None zurueckgeben"

    def test_parse_tool_call_invalid_json(self) -> None:
        """Malformed JSON gibt None."""
        registry = ToolRegistry()

        llm_output = '<tool_call>{invalid json}</tool_call>'

        tool_call = registry.parse_tool_call(llm_output)

        assert tool_call is None, "Invalides JSON sollte None zurueckgeben"

    def test_parse_tool_call_missing_fields(self) -> None:
        """Fehlende tool/params Felder gibt None."""
        registry = ToolRegistry()

        # Fehlendes "tool" Feld
        llm_output1 = '<tool_call>{"params": {"query": "test"}}</tool_call>'
        tool_call1 = registry.parse_tool_call(llm_output1)
        assert tool_call1 is None, "Fehlende tool sollte None geben"

        # Unknown tool name
        llm_output2 = '<tool_call>{"tool": "unknown_tool", "params": {}}</tool_call>'
        tool_call2 = registry.parse_tool_call(llm_output2)
        assert tool_call2 is None, "Unbekanntes Tool sollte None geben"

    def test_tool_definitions_have_german_descriptions(self) -> None:
        """Alle Beschreibungen sind nicht leer."""
        registry = ToolRegistry()

        all_tools = registry.get_tools_for_user("admin")

        for tool in all_tools:
            assert len(tool.description) > 0, f"Tool {tool.name} sollte Beschreibung haben"
            assert len(tool.parameters) > 0, f"Tool {tool.name} sollte Parameter haben"

    def test_destructive_tools_require_confirmation(self) -> None:
        """Destruktive Tools benoetigen Bestaetigung."""
        registry = ToolRegistry()

        destructive_tools = [
            "move_document",
            "tag_document",
            "categorize_document",
            "create_reminder",
        ]

        for tool_name in destructive_tools:
            tool = registry.get_tool(tool_name)
            assert tool is not None, f"Tool {tool_name} sollte existieren"
            assert tool.requires_confirmation is True, f"Tool {tool_name} sollte Bestaetigung brauchen"

    def test_parse_tool_call_with_whitespace(self) -> None:
        """Tool-Call mit Whitespace wird korrekt geparst."""
        registry = ToolRegistry()

        llm_output = '''
        <tool_call>
            {
                "tool": "search_documents",
                "params": {
                    "query": "test"
                }
            }
        </tool_call>
        '''

        tool_call = registry.parse_tool_call(llm_output)

        assert tool_call is not None, "Tool-Call mit Whitespace sollte geparst werden"
        assert tool_call.tool_name == "search_documents"

    def test_get_tools_for_unknown_level_defaults_to_viewer(self) -> None:
        """Unbekanntes User-Level gibt Viewer-Tools."""
        registry = ToolRegistry()

        tools = registry.get_tools_for_user("unknown_level")

        assert len(tools) == 4, "Unbekanntes Level sollte auf Viewer defaulten"

    def test_tool_to_json_schema(self) -> None:
        """Tool kann zu JSON Schema konvertiert werden."""
        registry = ToolRegistry()

        tool = registry.get_tool("search_documents")
        assert tool is not None

        schema = tool.to_json_schema()

        assert "name" in schema
        assert "description" in schema
        assert "parameters" in schema
        assert "requires_confirmation" in schema

        assert schema["name"] == "search_documents"
        assert schema["parameters"]["type"] == "object"
        assert "properties" in schema["parameters"]
        assert "required" in schema["parameters"]

    def test_singleton_factory(self) -> None:
        """get_tool_registry gibt Singleton zurueck."""
        registry1 = get_tool_registry()
        registry2 = get_tool_registry()

        assert registry1 is registry2, "Factory sollte Singleton zurueckgeben"


class TestToolCallDataclass:
    """Tests fuer ToolCall Dataclass."""

    def test_tool_call_creation(self) -> None:
        """ToolCall kann erstellt werden."""
        tool_call = ToolCall(
            tool_name="search_documents",
            parameters={"query": "test"}
        )

        assert tool_call.tool_name == "search_documents"
        assert tool_call.parameters == {"query": "test"}


class TestToolParameter:
    """Tests fuer ToolParameter."""

    def test_required_parameter(self) -> None:
        """Erforderliche Parameter werden validiert."""
        registry = ToolRegistry()

        search_tool = registry.get_tool("search_documents")
        assert search_tool is not None

        # query ist erforderlich
        query_param = next((p for p in search_tool.parameters if p.name == "query"), None)
        assert query_param is not None
        assert query_param.required is True
        assert query_param.type == ToolParameterType.STRING

    def test_optional_parameter(self) -> None:
        """Optionale Parameter sind nicht required."""
        registry = ToolRegistry()

        search_tool = registry.get_tool("search_documents")
        assert search_tool is not None

        # document_type ist optional
        doc_type_param = next((p for p in search_tool.parameters if p.name == "document_type"), None)
        assert doc_type_param is not None
        assert doc_type_param.required is False

    def test_array_parameter_has_items_type(self) -> None:
        """Array-Parameter haben items_type."""
        registry = ToolRegistry()

        tag_tool = registry.get_tool("tag_document")
        assert tag_tool is not None

        tags_param = next((p for p in tag_tool.parameters if p.name == "tags"), None)
        assert tags_param is not None
        assert tags_param.type == ToolParameterType.ARRAY
        assert tags_param.items_type == "string"
