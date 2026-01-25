"""Process Definition Service.

Verwaltet BPMN Prozess-Definitionen:
- Deploy: Neue Prozess-Version erstellen
- Activate/Deactivate: Prozess aktivieren/deaktivieren
- Export: BPMN XML exportieren
- List/Get: Prozesse abrufen
"""

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from uuid import UUID
import structlog

from sqlalchemy import select, update, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.bpmn_models.bpmn import (
    ProcessDefinition,
    ProcessInstance,
    ProcessStatus,
)
from app.services.bpmn.bpmn_parser import BPMNParser, BPMNProcess

logger = structlog.get_logger(__name__)


class ProcessDefinitionService:
    """Service fuer Prozess-Definitionen.

    Verwaltet den Lifecycle von BPMN Prozess-Definitionen:
    - Versionierung (auto-increment bei Deploy)
    - Aktivierung/Deaktivierung
    - BPMN XML Import/Export
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.parser = BPMNParser()

    async def deploy(
        self,
        key: str,
        name: str,
        company_id: UUID,
        bpmn_xml: Optional[str] = None,
        process_data: Optional[Dict[str, Any]] = None,
        description: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        deployed_by_id: Optional[UUID] = None,
        activate: bool = True,
    ) -> ProcessDefinition:
        """Deployt eine neue Prozess-Version.

        Wenn BPMN XML angegeben, wird es geparst und als process_data gespeichert.
        Version wird automatisch inkrementiert.

        Args:
            key: Eindeutiger Prozess-Schluessel
            name: Anzeigename
            company_id: Mandant
            bpmn_xml: Optional BPMN 2.0 XML
            process_data: Alternative: Bereits geparstes Process-Dict
            description: Beschreibung
            category: Kategorie fuer Filterung
            tags: Tags fuer Suche
            deployed_by_id: Deploying User
            activate: Direkt aktivieren (deaktiviert vorherige Version)

        Returns:
            Neue ProcessDefinition

        Raises:
            ValueError: Bei ungueltigem BPMN XML
        """
        # BPMN parsen falls angegeben
        parsed_data: Dict[str, Any] = {}
        if bpmn_xml:
            parsed_process = self.parser.parse(bpmn_xml)
            parsed_data = parsed_process.to_dict()
        elif process_data:
            parsed_data = process_data
        else:
            raise ValueError("Entweder bpmn_xml oder process_data erforderlich")

        # Naechste Version ermitteln
        next_version = await self._get_next_version(company_id, key)

        # Bei Aktivierung: Vorherige Version deaktivieren
        if activate:
            await self._deactivate_previous_versions(company_id, key)

        # Neue Definition erstellen
        definition = ProcessDefinition(
            key=key,
            name=name,
            description=description,
            version=next_version,
            is_active=activate,
            bpmn_xml=bpmn_xml,
            process_data=parsed_data,
            category=category,
            tags=tags or [],
            deployed_at=datetime.now(timezone.utc) if activate else None,
            deployed_by_id=deployed_by_id,
            company_id=company_id,
        )

        self.db.add(definition)
        await self.db.flush()

        logger.info(
            "process_definition_deployed",
            definition_id=str(definition.id),
            key=key,
            version=next_version,
            is_active=activate,
            company_id=str(company_id)
        )

        return definition

    async def deploy_from_json(
        self,
        key: str,
        name: str,
        company_id: UUID,
        process_json: Dict[str, Any],
        deployed_by_id: Optional[UUID] = None,
        **kwargs
    ) -> ProcessDefinition:
        """Deployt Prozess aus Frontend-JSON (React Flow Format).

        Konvertiert das Frontend-Format in BPMN-kompatible Struktur.

        Args:
            key: Prozess-Key
            name: Anzeigename
            company_id: Mandant
            process_json: React Flow JSON
            deployed_by_id: User
            **kwargs: Weitere Argumente fuer deploy()

        Returns:
            ProcessDefinition
        """
        # Frontend-JSON zu process_data konvertieren
        process_data = self._convert_frontend_json(process_json, key, name)

        return await self.deploy(
            key=key,
            name=name,
            company_id=company_id,
            process_data=process_data,
            deployed_by_id=deployed_by_id,
            **kwargs
        )

    def _convert_frontend_json(
        self,
        frontend_json: Dict[str, Any],
        process_id: str,
        process_name: str
    ) -> Dict[str, Any]:
        """Konvertiert React Flow JSON zu BPMN-kompatibler Struktur.

        React Flow Format:
        {
            "nodes": [{"id": "...", "type": "...", "data": {...}, ...}],
            "edges": [{"id": "...", "source": "...", "target": "...", ...}]
        }
        """
        elements = []

        # Nodes konvertieren
        for node in frontend_json.get("nodes", []):
            element = {
                "id": node["id"],
                "type": self._map_frontend_node_type(node.get("type", "task")),
                "name": node.get("data", {}).get("label"),
                "incoming": [],
                "outgoing": [],
            }

            # Node-spezifische Daten
            node_data = node.get("data", {})
            if "assignee" in node_data:
                element["assignee"] = node_data["assignee"]
            if "candidateGroups" in node_data:
                element["candidate_groups"] = node_data["candidateGroups"]
            if "formKey" in node_data:
                element["form_key"] = node_data["formKey"]
            if "timerType" in node_data:
                element["timer_type"] = node_data["timerType"]
                element["timer_value"] = node_data.get("timerValue")
            if "condition" in node_data:
                element["condition"] = node_data["condition"]
            if "implementation" in node_data:
                element["implementation"] = node_data["implementation"]

            elements.append(element)

        # Edges (Sequence Flows) konvertieren
        elements_by_id = {e["id"]: e for e in elements}

        for edge in frontend_json.get("edges", []):
            flow_element = {
                "id": edge["id"],
                "type": "sequenceFlow",
                "source_ref": edge["source"],
                "target_ref": edge["target"],
            }

            # Condition Expression
            if edge.get("data", {}).get("condition"):
                flow_element["condition"] = edge["data"]["condition"]

            # Default Flow Marker
            if edge.get("data", {}).get("isDefault"):
                flow_element["is_default"] = True

            elements.append(flow_element)

            # Incoming/Outgoing aktualisieren
            source = elements_by_id.get(edge["source"])
            target = elements_by_id.get(edge["target"])

            if source:
                source["outgoing"].append(edge["id"])
            if target:
                target["incoming"].append(edge["id"])

        return {
            "id": process_id,
            "name": process_name,
            "is_executable": True,
            "elements": elements,
        }

    def _map_frontend_node_type(self, frontend_type: str) -> str:
        """Mappt Frontend Node-Typen zu BPMN-Typen."""
        mapping = {
            "startEvent": "startEvent",
            "endEvent": "endEvent",
            "task": "userTask",
            "userTask": "userTask",
            "serviceTask": "serviceTask",
            "scriptTask": "scriptTask",
            "exclusiveGateway": "exclusiveGateway",
            "parallelGateway": "parallelGateway",
            "inclusiveGateway": "inclusiveGateway",
            "timerEvent": "intermediateCatchEvent",
            "subProcess": "subProcess",
        }
        return mapping.get(frontend_type, "userTask")

    async def get_by_id(
        self,
        definition_id: UUID,
        company_id: UUID
    ) -> Optional[ProcessDefinition]:
        """Prozess-Definition nach ID abrufen."""
        query = select(ProcessDefinition).where(
            and_(
                ProcessDefinition.id == definition_id,
                ProcessDefinition.company_id == company_id
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_active_by_key(
        self,
        key: str,
        company_id: UUID
    ) -> Optional[ProcessDefinition]:
        """Aktive Prozess-Definition nach Key abrufen."""
        query = select(ProcessDefinition).where(
            and_(
                ProcessDefinition.key == key,
                ProcessDefinition.company_id == company_id,
                ProcessDefinition.is_active == True
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def list_definitions(
        self,
        company_id: UUID,
        category: Optional[str] = None,
        only_active: bool = False,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[List[ProcessDefinition], int]:
        """Listet Prozess-Definitionen auf.

        Args:
            company_id: Mandant
            category: Filter nach Kategorie
            only_active: Nur aktive Versionen
            page: Seite (1-basiert)
            per_page: Eintraege pro Seite

        Returns:
            (Liste von Definitionen, Gesamtanzahl)
        """
        # Base Query
        conditions = [ProcessDefinition.company_id == company_id]

        if category:
            conditions.append(ProcessDefinition.category == category)

        if only_active:
            conditions.append(ProcessDefinition.is_active == True)

        # Count Query
        count_query = select(func.count(ProcessDefinition.id)).where(
            and_(*conditions)
        )
        total = await self.db.scalar(count_query)

        # Data Query
        query = (
            select(ProcessDefinition)
            .where(and_(*conditions))
            .order_by(ProcessDefinition.key, ProcessDefinition.version.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        result = await self.db.execute(query)
        definitions = list(result.scalars().all())

        return definitions, total or 0

    async def activate(
        self,
        definition_id: UUID,
        company_id: UUID,
        user_id: Optional[UUID] = None
    ) -> ProcessDefinition:
        """Aktiviert eine Prozess-Definition.

        Deaktiviert automatisch andere Versionen desselben Keys.

        Args:
            definition_id: Zu aktivierende Definition
            company_id: Mandant
            user_id: Aktivierender User

        Returns:
            Aktivierte Definition

        Raises:
            ValueError: Wenn Definition nicht gefunden
        """
        definition = await self.get_by_id(definition_id, company_id)
        if not definition:
            raise ValueError("Prozess-Definition nicht gefunden")

        # Andere Versionen deaktivieren
        await self._deactivate_previous_versions(company_id, definition.key)

        # Diese Version aktivieren
        definition.is_active = True
        definition.deployed_at = datetime.now(timezone.utc)
        definition.deployed_by_id = user_id

        await self.db.flush()

        logger.info(
            "process_definition_activated",
            definition_id=str(definition_id),
            key=definition.key,
            version=definition.version
        )

        return definition

    async def deactivate(
        self,
        definition_id: UUID,
        company_id: UUID
    ) -> ProcessDefinition:
        """Deaktiviert eine Prozess-Definition.

        Verhindert das Starten neuer Instanzen.

        Args:
            definition_id: Zu deaktivierende Definition
            company_id: Mandant

        Returns:
            Deaktivierte Definition
        """
        definition = await self.get_by_id(definition_id, company_id)
        if not definition:
            raise ValueError("Prozess-Definition nicht gefunden")

        definition.is_active = False
        await self.db.flush()

        logger.info(
            "process_definition_deactivated",
            definition_id=str(definition_id),
            key=definition.key
        )

        return definition

    async def export_bpmn(
        self,
        definition_id: UUID,
        company_id: UUID
    ) -> str:
        """Exportiert Prozess-Definition als BPMN 2.0 XML.

        Args:
            definition_id: Definition ID
            company_id: Mandant

        Returns:
            BPMN 2.0 XML String

        Raises:
            ValueError: Wenn Definition nicht gefunden
        """
        definition = await self.get_by_id(definition_id, company_id)
        if not definition:
            raise ValueError("Prozess-Definition nicht gefunden")

        # Wenn BPMN XML gespeichert, direkt zurueckgeben
        if definition.bpmn_xml:
            return definition.bpmn_xml

        # Ansonsten aus process_data generieren
        process = BPMNProcess.from_dict(definition.process_data)
        return self.parser.generate(process)

    async def get_statistics(
        self,
        company_id: UUID
    ) -> Dict[str, Any]:
        """Gibt Statistiken zu Prozess-Definitionen zurueck."""
        # Anzahl Definitionen
        def_count = await self.db.scalar(
            select(func.count(ProcessDefinition.id)).where(
                ProcessDefinition.company_id == company_id
            )
        )

        # Anzahl aktive Definitionen
        active_count = await self.db.scalar(
            select(func.count(ProcessDefinition.id)).where(
                and_(
                    ProcessDefinition.company_id == company_id,
                    ProcessDefinition.is_active == True
                )
            )
        )

        # Anzahl laufende Instanzen
        running_count = await self.db.scalar(
            select(func.count(ProcessInstance.id)).where(
                and_(
                    ProcessInstance.company_id == company_id,
                    ProcessInstance.status == ProcessStatus.RUNNING
                )
            )
        )

        # Kategorien
        categories_query = (
            select(
                ProcessDefinition.category,
                func.count(ProcessDefinition.id).label("count")
            )
            .where(
                and_(
                    ProcessDefinition.company_id == company_id,
                    ProcessDefinition.is_active == True
                )
            )
            .group_by(ProcessDefinition.category)
        )
        categories_result = await self.db.execute(categories_query)
        categories = {
            row.category or "Ohne Kategorie": row.count
            for row in categories_result
        }

        return {
            "total_definitions": def_count or 0,
            "active_definitions": active_count or 0,
            "running_instances": running_count or 0,
            "categories": categories,
        }

    async def _get_next_version(
        self,
        company_id: UUID,
        key: str
    ) -> int:
        """Ermittelt die naechste Versionsnummer."""
        max_version = await self.db.scalar(
            select(func.max(ProcessDefinition.version)).where(
                and_(
                    ProcessDefinition.company_id == company_id,
                    ProcessDefinition.key == key
                )
            )
        )
        return (max_version or 0) + 1

    async def _deactivate_previous_versions(
        self,
        company_id: UUID,
        key: str
    ) -> None:
        """Deaktiviert alle Versionen eines Prozess-Keys."""
        await self.db.execute(
            update(ProcessDefinition)
            .where(
                and_(
                    ProcessDefinition.company_id == company_id,
                    ProcessDefinition.key == key,
                    ProcessDefinition.is_active == True
                )
            )
            .values(is_active=False)
        )


def get_process_definition_service(db: AsyncSession) -> ProcessDefinitionService:
    """Factory Function fuer ProcessDefinitionService."""
    return ProcessDefinitionService(db)
