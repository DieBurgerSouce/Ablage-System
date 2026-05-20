"""
Document Template Service

Service für Dokumenten-Vorlagen mit:
- Template-CRUD
- Dokumentengenerierung mit Jinja2
- PDF-Rendering
- Variablen-Validierung
"""

from __future__ import annotations

import io
import structlog
import re
import uuid
from datetime import datetime
from jinja2 import Environment, BaseLoader, TemplateSyntaxError, UndefinedError
from sqlalchemy import and_, or_, select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    DocumentTemplate,
    GeneratedDocument,
    TemplateSnippet,
    TemplateCategory,
    TemplateOutputFormat,
    VariableType,
)

logger = structlog.get_logger(__name__)


class TemplateValidationError(Exception):
    """Fehler bei Template-Validierung."""
    pass


class TemplateRenderError(Exception):
    """Fehler beim Rendern eines Templates."""
    pass


class DocumentTemplateService:
    """Service für Dokumenten-Vorlagen."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._jinja_env = Environment(
            loader=BaseLoader(),
            autoescape=True,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        # Custom Jinja2 Filter registrieren
        self._register_custom_filters()

    def _register_custom_filters(self) -> None:
        """Registriere benutzerdefinierte Jinja2-Filter."""

        def format_currency(value: float, currency: str = "EUR") -> str:
            """Formatiert Währungswerte deutsch."""
            if value is None:
                return ""
            formatted = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            return f"{formatted} {currency}"

        def format_date(value: datetime | str, fmt: str = "%d.%m.%Y") -> str:
            """Formatiert Datum deutsch."""
            if value is None:
                return ""
            if isinstance(value, str):
                try:
                    value = datetime.fromisoformat(value)
                except ValueError:
                    return value
            return value.strftime(fmt)

        def format_number(value: float, decimals: int = 2) -> str:
            """Formatiert Zahlen deutsch."""
            if value is None:
                return ""
            formatted = f"{value:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")
            return formatted

        self._jinja_env.filters["currency"] = format_currency
        self._jinja_env.filters["date"] = format_date
        self._jinja_env.filters["number"] = format_number

    # =========================================================================
    # Template CRUD
    # =========================================================================

    async def create_template(
        self,
        company_id: uuid.UUID,
        name: str,
        code: str,
        content: str,
        category: TemplateCategory | str = TemplateCategory.OTHER,
        variables: list[dict[str, object]] | None = None,
        description: str | None = None,
        created_by_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,  # Alias for created_by_id
        **kwargs: object,
    ) -> DocumentTemplate:
        """Erstellt eine neue Dokumentvorlage."""
        # Validiere Template-Syntax
        self._validate_template_syntax(content)

        # Validiere Variablen-Schema
        if variables:
            self._validate_variables_schema(variables)

        # Prüfe ob Code bereits existiert
        existing = await self.get_template_by_code(company_id, code)
        if existing:
            raise TemplateValidationError(f"Template mit Code '{code}' existiert bereits")

        # Handle category as string
        if isinstance(category, str):
            category = TemplateCategory(category)

        # Use user_id as fallback for created_by_id
        final_created_by_id = created_by_id or user_id

        template = DocumentTemplate(
            company_id=company_id,
            name=name,
            code=code,
            content=content,
            category=category,
            variables=variables or [],
            description=description,
            created_by_id=final_created_by_id,
            **kwargs,
        )

        self.db.add(template)
        await self.db.flush()
        await self.db.refresh(template)

        logger.info(f"Template erstellt: {template.code} (ID: {template.id})")
        return template

    async def get_template(
        self,
        template_id: uuid.UUID,
        company_id: uuid.UUID | None = None,
    ) -> DocumentTemplate | None:
        """Holt eine Vorlage per ID."""
        query = select(DocumentTemplate).where(DocumentTemplate.id == template_id)
        if company_id:
            query = query.where(DocumentTemplate.company_id == company_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_template_by_code(
        self,
        company_id: uuid.UUID,
        code: str,
    ) -> DocumentTemplate | None:
        """Holt eine Vorlage per Code."""
        result = await self.db.execute(
            select(DocumentTemplate).where(
                and_(
                    DocumentTemplate.company_id == company_id,
                    DocumentTemplate.code == code,
                    DocumentTemplate.is_latest == True,
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_templates(
        self,
        company_id: uuid.UUID,
        category: TemplateCategory | str | None = None,
        search: str | None = None,
        include_inactive: bool = False,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[DocumentTemplate], int]:
        """Listet Vorlagen mit Filtern."""
        query = select(DocumentTemplate).where(
            and_(
                DocumentTemplate.company_id == company_id,
                DocumentTemplate.is_latest == True,
            )
        )
        count_query = select(func.count(DocumentTemplate.id)).where(
            and_(
                DocumentTemplate.company_id == company_id,
                DocumentTemplate.is_latest == True,
            )
        )

        if category:
            # Handle string or enum category
            if isinstance(category, str):
                query = query.where(DocumentTemplate.category == category)
                count_query = count_query.where(DocumentTemplate.category == category)
            else:
                query = query.where(DocumentTemplate.category == category)
                count_query = count_query.where(DocumentTemplate.category == category)

        if not include_inactive:
            query = query.where(DocumentTemplate.is_active == True)
            count_query = count_query.where(DocumentTemplate.is_active == True)

        if search:
            search_filter = or_(
                DocumentTemplate.name.ilike(f"%{search}%"),
                DocumentTemplate.code.ilike(f"%{search}%"),
                DocumentTemplate.description.ilike(f"%{search}%"),
            )
            query = query.where(search_filter)
            count_query = count_query.where(search_filter)

        # Sortierung: Default-Templates zuerst, dann nach Nutzung
        query = query.order_by(
            DocumentTemplate.is_default.desc(),
            DocumentTemplate.usage_count.desc(),
            DocumentTemplate.name,
        )
        query = query.offset(offset).limit(limit)

        result = await self.db.execute(query)
        templates = list(result.scalars().all())

        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        return templates, total

    async def update_template(
        self,
        template_id: uuid.UUID,
        company_id: uuid.UUID | None = None,
        create_new_version: bool = False,
        **updates: object,
    ) -> DocumentTemplate | None:
        """
        Aktualisiert eine Vorlage.

        Bei create_new_version=True wird eine neue Version erstellt,
        die alte Version bleibt erhalten.
        """
        template = await self.get_template(template_id, company_id)
        if not template:
            return None

        if create_new_version:
            # Alte Version als nicht-latest markieren
            await self.db.execute(
                update(DocumentTemplate)
                .where(DocumentTemplate.id == template_id)
                .values(is_latest=False)
            )

            # Neue Version erstellen
            new_template = DocumentTemplate(
                company_id=template.company_id,
                name=updates.get("name", template.name),
                code=template.code,
                description=updates.get("description", template.description),
                category=updates.get("category", template.category),
                content=updates.get("content", template.content),
                header_content=updates.get("header_content", template.header_content),
                footer_content=updates.get("footer_content", template.footer_content),
                css_styles=updates.get("css_styles", template.css_styles),
                page_size=updates.get("page_size", template.page_size),
                orientation=updates.get("orientation", template.orientation),
                margins=updates.get("margins", template.margins),
                output_format=updates.get("output_format", template.output_format),
                variables=updates.get("variables", template.variables),
                version=template.version + 1,
                is_latest=True,
                parent_template_id=template.id,
                is_active=template.is_active,
                is_default=template.is_default,
                tags=updates.get("tags", template.tags),
                template_metadata=updates.get("template_metadata", template.template_metadata),
                created_by_id=updates.get("created_by_id"),
            )

            # Validiere neue Inhalte
            if "content" in updates:
                self._validate_template_syntax(updates["content"])
            if "variables" in updates:
                self._validate_variables_schema(updates["variables"])

            self.db.add(new_template)
            await self.db.flush()
            await self.db.refresh(new_template)

            logger.info(f"Template neue Version erstellt: {new_template.code} v{new_template.version}")
            return new_template
        else:
            # Direkte Aktualisierung
            if "content" in updates:
                self._validate_template_syntax(updates["content"])
            if "variables" in updates:
                self._validate_variables_schema(updates["variables"])

            for key, value in updates.items():
                if hasattr(template, key):
                    setattr(template, key, value)

            await self.db.flush()
            await self.db.refresh(template)

            logger.info(f"Template aktualisiert: {template.code}")
            return template

    async def delete_template(
        self,
        template_id: uuid.UUID,
        company_id: uuid.UUID | None = None,
    ) -> bool:
        """Löscht eine Vorlage (Soft-Delete via is_active)."""
        template = await self.get_template(template_id, company_id)
        if not template:
            return False

        template.is_active = False
        await self.db.flush()

        logger.info(f"Template deaktiviert: {template.code}")
        return True

    # =========================================================================
    # Dokumentengenerierung
    # =========================================================================

    async def render_template(
        self,
        template: DocumentTemplate | None = None,
        template_id: uuid.UUID | None = None,
        variables: dict[str, object] | None = None,
        preview: bool = False,
    ) -> str:
        """
        Rendert ein Template mit den gegebenen Variablen.

        Bei preview=True werden fehlende Variablen durch Platzhalter ersetzt.
        Kann entweder template Objekt oder template_id erhalten.
        """
        variables = variables or {}

        # Support both template object and template_id
        if template is None and template_id is not None:
            template = await self.get_template(template_id)

        if not template:
            raise TemplateValidationError("Template nicht gefunden")

        # Validiere Variablen
        if not preview:
            self._validate_variables(template.variables, variables)

        # Snippets laden und einfügen
        rendered_content = await self._resolve_snippets(template.company_id, template.content)

        # Header und Footer verarbeiten
        header = ""
        footer = ""
        if template.header_content:
            header = await self._resolve_snippets(template.company_id, template.header_content)
        if template.footer_content:
            footer = await self._resolve_snippets(template.company_id, template.footer_content)

        try:
            # Jinja2 Template rendern
            jinja_template = self._jinja_env.from_string(rendered_content)

            # Standard-Variablen hinzufuegen
            render_vars = {
                **variables,
                "heute": datetime.now(),
                "firma": await self._get_company_data(template.company_id),
            }

            # Bei Preview: Undefined-Handler
            if preview:
                render_vars = self._add_preview_defaults(template.variables, render_vars)

            rendered = jinja_template.render(**render_vars)

            # Header/Footer rendern
            if header:
                header_template = self._jinja_env.from_string(header)
                header = header_template.render(**render_vars)
            if footer:
                footer_template = self._jinja_env.from_string(footer)
                footer = footer_template.render(**render_vars)

            # HTML-Dokument zusammenbauen
            html = self._build_html_document(
                content=rendered,
                header=header,
                footer=footer,
                css=template.css_styles,
                page_size=template.page_size,
                orientation=template.orientation,
                margins=template.margins,
            )

            return html

        except UndefinedError as e:
            raise TemplateRenderError(f"Fehlende Variable: {e}")
        except TemplateSyntaxError as e:
            raise TemplateRenderError(f"Template-Syntax-Fehler: {e}")

    async def generate_document(
        self,
        template: DocumentTemplate | None = None,
        template_id: uuid.UUID | None = None,
        company_id: uuid.UUID | None = None,
        title: str = "",
        variables: dict[str, object] | None = None,
        created_by_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,  # Alias for created_by_id
        linked_entity_id: uuid.UUID | None = None,
        linked_document_id: uuid.UUID | None = None,
        save_to_storage: bool = True,
    ) -> GeneratedDocument:
        """
        Generiert ein Dokument aus einer Vorlage.

        Rendert das Template und speichert das Ergebnis.
        Kann entweder template Objekt oder template_id erhalten.
        """
        variables = variables or {}

        # Support both template object and template_id
        if template is None and template_id is not None:
            template = await self.get_template(template_id, company_id)

        if not template:
            raise TemplateValidationError("Template nicht gefunden")

        # Use company_id from template if not provided
        company_id = company_id or template.company_id

        # Validiere Variablen
        self._validate_variables(template.variables, variables)

        # Use user_id as fallback for created_by_id
        final_created_by_id = created_by_id or user_id

        # Template rendern
        html_content = await self.render_template(template=template, variables=variables, preview=False)

        # Dateiname generieren
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_title = re.sub(r"[^\w\s-]", "", title).strip().replace(" ", "_")[:50]
        extension = template.output_format.value
        filename = f"{safe_title}_{timestamp}.{extension}"

        # PDF generieren falls gewünscht
        file_content: bytes | None = None
        file_size: int | None = None
        storage_path: str | None = None

        if template.output_format == TemplateOutputFormat.PDF and save_to_storage:
            file_content = await self._render_pdf(html_content)
            file_size = len(file_content)
            # Phase 11.4: MinIO Storage Integration
            storage_path = await self._save_to_storage(company_id, filename, file_content)

        # GeneratedDocument erstellen
        doc = GeneratedDocument(
            company_id=company_id,
            template_id=template.id,
            title=title,
            filename=filename,
            storage_path=storage_path,
            file_size=file_size,
            variable_values=variables,
            template_version=template.version,
            linked_entity_id=linked_entity_id,
            linked_document_id=linked_document_id,
            created_by_id=final_created_by_id,
        )

        self.db.add(doc)

        # Template-Nutzung aktualisieren
        template.usage_count += 1
        template.last_used_at = datetime.now()

        await self.db.flush()
        await self.db.refresh(doc)

        logger.info(f"Dokument generiert: {doc.title} aus Template {template.code}")
        return doc

    # =========================================================================
    # Snippets
    # =========================================================================

    async def create_snippet(
        self,
        company_id: uuid.UUID,
        name: str,
        code: str,
        content: str,
        category: str = "general",
        description: str | None = None,
    ) -> TemplateSnippet:
        """Erstellt einen wiederverwendbaren Textbaustein."""
        snippet = TemplateSnippet(
            company_id=company_id,
            name=name,
            code=code,
            content=content,
            category=category,
            description=description,
        )

        self.db.add(snippet)
        await self.db.flush()
        await self.db.refresh(snippet)

        return snippet

    async def list_snippets(
        self,
        company_id: uuid.UUID,
        category: str | None = None,
        search: str | None = None,
    ) -> list[TemplateSnippet]:
        """Listet verfügbare Snippets."""
        query = select(TemplateSnippet).where(
            and_(
                TemplateSnippet.company_id == company_id,
                TemplateSnippet.is_active == True,
            )
        )

        if category:
            query = query.where(TemplateSnippet.category == category)

        if search:
            search_filter = or_(
                TemplateSnippet.name.ilike(f"%{search}%"),
                TemplateSnippet.code.ilike(f"%{search}%"),
            )
            query = query.where(search_filter)

        query = query.order_by(TemplateSnippet.name)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_snippet(
        self,
        snippet_id: uuid.UUID,
        company_id: uuid.UUID | None = None,
    ) -> TemplateSnippet | None:
        """Holt einen Snippet per ID."""
        query = select(TemplateSnippet).where(TemplateSnippet.id == snippet_id)
        if company_id:
            query = query.where(TemplateSnippet.company_id == company_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def update_snippet(
        self,
        snippet_id: uuid.UUID,
        company_id: uuid.UUID | None = None,
        **updates: object,
    ) -> TemplateSnippet | None:
        """Aktualisiert einen Snippet."""
        snippet = await self.get_snippet(snippet_id, company_id)
        if not snippet:
            return None

        for key, value in updates.items():
            if hasattr(snippet, key) and value is not None:
                setattr(snippet, key, value)

        await self.db.flush()
        await self.db.refresh(snippet)

        logger.info(f"Snippet aktualisiert: {snippet.code}")
        return snippet

    async def delete_snippet(
        self,
        snippet_id: uuid.UUID,
        company_id: uuid.UUID | None = None,
    ) -> bool:
        """Deaktiviert einen Snippet (Soft-Delete)."""
        snippet = await self.get_snippet(snippet_id, company_id)
        if not snippet:
            return False

        snippet.is_active = False
        await self.db.flush()

        logger.info(f"Snippet deaktiviert: {snippet.code}")
        return True

    # =========================================================================
    # Generated Documents
    # =========================================================================

    async def list_generated_documents(
        self,
        company_id: uuid.UUID,
        template_id: uuid.UUID | None = None,
        entity_id: uuid.UUID | None = None,
        search: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[GeneratedDocument], int]:
        """Listet generierte Dokumente mit Filtern."""
        query = select(GeneratedDocument).where(
            GeneratedDocument.company_id == company_id
        )
        count_query = select(func.count(GeneratedDocument.id)).where(
            GeneratedDocument.company_id == company_id
        )

        if template_id:
            query = query.where(GeneratedDocument.template_id == template_id)
            count_query = count_query.where(GeneratedDocument.template_id == template_id)

        if entity_id:
            query = query.where(GeneratedDocument.linked_entity_id == entity_id)
            count_query = count_query.where(GeneratedDocument.linked_entity_id == entity_id)

        if search:
            search_filter = or_(
                GeneratedDocument.title.ilike(f"%{search}%"),
                GeneratedDocument.filename.ilike(f"%{search}%"),
            )
            query = query.where(search_filter)
            count_query = count_query.where(search_filter)

        # Neueste zuerst
        query = query.order_by(GeneratedDocument.created_at.desc())
        query = query.offset(offset).limit(limit)

        result = await self.db.execute(query)
        documents = list(result.scalars().all())

        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        return documents, total

    async def get_generated_document(
        self,
        document_id: uuid.UUID,
        company_id: uuid.UUID | None = None,
    ) -> GeneratedDocument | None:
        """Holt ein generiertes Dokument per ID."""
        query = select(GeneratedDocument).where(GeneratedDocument.id == document_id)
        if company_id:
            query = query.where(GeneratedDocument.company_id == company_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    # =========================================================================
    # Category Summary
    # =========================================================================

    async def get_category_summary(
        self,
        company_id: uuid.UUID,
    ) -> list[dict[str, object]]:
        """Gibt eine Zusammenfassung der Vorlagen pro Kategorie zurück."""
        # Get all categories with counts
        result = await self.db.execute(
            select(
                DocumentTemplate.category,
                func.count(DocumentTemplate.id).label("count"),
            )
            .where(
                and_(
                    DocumentTemplate.company_id == company_id,
                    DocumentTemplate.is_latest == True,
                    DocumentTemplate.is_active == True,
                )
            )
            .group_by(DocumentTemplate.category)
        )

        category_counts = {row.category: row.count for row in result}

        # Get default templates per category
        default_result = await self.db.execute(
            select(DocumentTemplate)
            .where(
                and_(
                    DocumentTemplate.company_id == company_id,
                    DocumentTemplate.is_latest == True,
                    DocumentTemplate.is_active == True,
                    DocumentTemplate.is_default == True,
                )
            )
        )

        default_templates = {t.category: t for t in default_result.scalars().all()}

        # Build summary for all categories that have templates
        summary = []
        for category in TemplateCategory:
            count = category_counts.get(category, 0)
            if count > 0:
                default_template = default_templates.get(category)
                summary.append({
                    "category": category.value,
                    "count": count,
                    "default_template_id": default_template.id if default_template else None,
                    "default_template_name": default_template.name if default_template else None,
                })

        return summary

    # =========================================================================
    # Variable Validation (Public API)
    # =========================================================================

    def validate_variables(
        self,
        template: DocumentTemplate,
        variables: dict[str, object],
    ) -> tuple[bool, list[str]]:
        """
        Validiert Variablen gegen das Template-Schema.

        Gibt zurück: (is_valid, list_of_error_messages)
        """
        errors: list[str] = []

        for var_def in template.variables or []:
            name = var_def.get("name", "")
            var_type = var_def.get("type", "")
            required = var_def.get("required", False)
            label = var_def.get("label", name)

            # Required check
            if required and (name not in variables or variables[name] is None):
                errors.append(f"Pflichtfeld '{label}' fehlt")
                continue

            if name in variables and variables[name] is not None:
                value = variables[name]

                # Type validation
                if var_type == VariableType.NUMBER.value:
                    if not isinstance(value, (int, float)):
                        errors.append(f"'{label}' muss eine Zahl sein")
                elif var_type == VariableType.CURRENCY.value:
                    if not isinstance(value, (int, float)):
                        errors.append(f"'{label}' muss ein Währungsbetrag sein")
                elif var_type == VariableType.DATE.value:
                    if not isinstance(value, (datetime, str)):
                        errors.append(f"'{label}' muss ein Datum sein")
                elif var_type == VariableType.BOOLEAN.value:
                    if not isinstance(value, bool):
                        errors.append(f"'{label}' muss ein Boolean sein")
                elif var_type == VariableType.SELECT.value:
                    options = var_def.get("options", [])
                    if options and value not in options:
                        errors.append(f"'{label}' muss einer der Werte sein: {', '.join(options)}")

        return len(errors) == 0, errors

    async def _resolve_snippets(self, company_id: uuid.UUID, content: str) -> str:
        """
        Ersetzt Snippet-Referenzen im Template.

        Format: {% snippet "CODE" %}
        """
        snippet_pattern = r'\{%\s*snippet\s+"([^"]+)"\s*%\}'
        matches = re.findall(snippet_pattern, content)

        if not matches:
            return content

        # Snippets laden
        snippets = await self.list_snippets(company_id)
        snippet_map = {s.code: s.content for s in snippets}

        # Ersetzen
        def replace_snippet(match: re.Match) -> str:
            code = match.group(1)
            return snippet_map.get(code, f"[Snippet '{code}' nicht gefunden]")

        return re.sub(snippet_pattern, replace_snippet, content)

    # =========================================================================
    # Validierung
    # =========================================================================

    def _validate_template_syntax(self, content: str) -> None:
        """Validiert Jinja2-Template-Syntax."""
        try:
            self._jinja_env.parse(content)
        except TemplateSyntaxError as e:
            raise TemplateValidationError(f"Ungültige Template-Syntax: {e}")

    def _validate_variables_schema(self, variables: list[dict[str, object]]) -> None:
        """Validiert das Variablen-Schema."""
        required_fields = {"name", "type"}
        valid_types = {t.value for t in VariableType}

        for var in variables:
            if not isinstance(var, dict):
                raise TemplateValidationError("Variable muss ein Dictionary sein")

            missing = required_fields - set(var.keys())
            if missing:
                raise TemplateValidationError(f"Fehlende Felder in Variable: {missing}")

            if var["type"] not in valid_types:
                raise TemplateValidationError(f"Ungültiger Variablentyp: {var['type']}")

            # Name validieren (nur alphanumerisch und Unterstrich)
            if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", var["name"]):
                raise TemplateValidationError(f"Ungültiger Variablenname: {var['name']}")

    def _validate_variables(
        self,
        schema: list[dict[str, object]],
        values: dict[str, object],
    ) -> None:
        """Validiert Variablen-Werte gegen das Schema."""
        for var_def in schema:
            name = var_def["name"]
            var_type = var_def["type"]
            required = var_def.get("required", False)

            if required and name not in values:
                raise TemplateValidationError(f"Pflichtfeld fehlt: {name}")

            if name in values and values[name] is not None:
                value = values[name]

                # Typ-Validierung
                if var_type == VariableType.NUMBER.value:
                    if not isinstance(value, (int, float)):
                        raise TemplateValidationError(f"{name} muss eine Zahl sein")
                elif var_type == VariableType.CURRENCY.value:
                    if not isinstance(value, (int, float)):
                        raise TemplateValidationError(f"{name} muss ein Währungsbetrag sein")
                elif var_type == VariableType.DATE.value:
                    if not isinstance(value, (datetime, str)):
                        raise TemplateValidationError(f"{name} muss ein Datum sein")
                elif var_type == VariableType.BOOLEAN.value:
                    if not isinstance(value, bool):
                        raise TemplateValidationError(f"{name} muss ein Boolean sein")
                elif var_type == VariableType.SELECT.value:
                    options = var_def.get("options", [])
                    if options and value not in options:
                        raise TemplateValidationError(f"{name} muss einer der Werte sein: {options}")

    def _add_preview_defaults(
        self,
        schema: list[dict[str, object]],
        values: dict[str, object],
    ) -> dict[str, object]:
        """Fuegt Platzhalter-Werte für Preview hinzu."""
        result = dict(values)

        for var_def in schema:
            name = var_def["name"]
            var_type = var_def["type"]
            label = var_def.get("label", name)

            if name not in result:
                # Platzhalter basierend auf Typ
                if var_type == VariableType.TEXT.value:
                    result[name] = f"[{label}]"
                elif var_type == VariableType.NUMBER.value:
                    result[name] = 0
                elif var_type == VariableType.CURRENCY.value:
                    result[name] = 0.00
                elif var_type == VariableType.DATE.value:
                    result[name] = datetime.now()
                elif var_type == VariableType.BOOLEAN.value:
                    result[name] = False
                elif var_type == VariableType.SELECT.value:
                    options = var_def.get("options", [])
                    result[name] = options[0] if options else f"[{label}]"
                elif var_type == VariableType.ENTITY.value:
                    result[name] = {"id": None, "name": f"[{label}]"}
                else:
                    result[name] = f"[{label}]"

        return result

    # =========================================================================
    # Hilfsmethoden
    # =========================================================================

    async def _get_company_data(self, company_id: uuid.UUID) -> dict[str, object]:
        """Laedt Firmendaten für Template-Variablen."""
        from app.db.models.company import Company

        result = await self.db.execute(
            select(Company).where(Company.id == company_id)
        )
        company = result.scalar_one_or_none()

        if not company:
            return {}

        return {
            "name": company.name,
            "address": company.address,
            "email": company.email,
            "phone": company.phone,
            "website": getattr(company, "website", None),
            "tax_id": getattr(company, "tax_id", None),
            "vat_id": getattr(company, "vat_id", None),
        }

    def _build_html_document(
        self,
        content: str,
        header: str = "",
        footer: str = "",
        css: str | None = None,
        page_size: str = "A4",
        orientation: str = "portrait",
        margins: dict[str, int] | None = None,
    ) -> str:
        """Baut ein vollständiges HTML-Dokument zusammen."""
        margins = margins or {"top": 20, "right": 15, "bottom": 20, "left": 15}

        # Page-Size CSS
        page_width = "210mm" if page_size == "A4" else "8.5in"
        page_height = "297mm" if page_size == "A4" else "11in"

        if orientation == "landscape":
            page_width, page_height = page_height, page_width

        default_css = f"""
        @page {{
            size: {page_width} {page_height};
            margin: {margins['top']}mm {margins['right']}mm {margins['bottom']}mm {margins['left']}mm;
        }}
        body {{
            font-family: 'Helvetica Neue', Arial, sans-serif;
            font-size: 11pt;
            line-height: 1.5;
            color: #333;
        }}
        .header {{
            margin-bottom: 20mm;
        }}
        .footer {{
            margin-top: 20mm;
            font-size: 9pt;
            color: #666;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 10px 0;
        }}
        th, td {{
            padding: 8px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background-color: #f5f5f5;
            font-weight: bold;
        }}
        """

        custom_css = css or ""

        html = f"""<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
{default_css}
{custom_css}
    </style>
</head>
<body>
    {f'<div class="header">{header}</div>' if header else ''}
    <div class="content">
{content}
    </div>
    {f'<div class="footer">{footer}</div>' if footer else ''}
</body>
</html>"""

        return html

    async def _save_to_storage(
        self,
        company_id: uuid.UUID,
        filename: str,
        file_content: bytes,
    ) -> str | None:
        """
        Speichert generiertes Dokument in MinIO.

        Phase 11.4: Vollständige MinIO-Integration für Template-Output.

        Args:
            company_id: Firmen-ID für Bucket-Isolierung
            filename: Dateiname des generierten Dokuments
            file_content: PDF-Bytes

        Returns:
            storage_path (s3://<bucket>/<key>) oder None bei Fehler
        """
        try:
            from app.services.storage_service import get_storage_service

            storage = get_storage_service()

            if not storage.available:
                logger.warning(
                    "minio_not_available_for_template_storage",
                    company_id=str(company_id),
                    filename=filename,
                )
                return None

            # Upload mit firmenspezifischem Pfad
            result = await storage.upload_document(
                file_data=file_content,
                filename=filename,
                content_type="application/pdf",
                user_id=f"templates/{company_id}",
                metadata={
                    "source": "document_template",
                    "company_id": str(company_id),
                    "generated_at": datetime.now().isoformat(),
                },
            )

            if result.get("success"):
                storage_path = f"s3://{result['bucket']}/{result['storage_path']}"
                logger.info(
                    "template_document_stored",
                    company_id=str(company_id),
                    filename=filename,
                    storage_path=storage_path,
                    size_bytes=result.get("size_bytes"),
                )
                return storage_path
            else:
                logger.warning(
                    "template_document_storage_failed",
                    company_id=str(company_id),
                    filename=filename,
                )
                return None

        except Exception as e:
            logger.error(
                f"template_storage_error: {e}",
                company_id=str(company_id),
                filename=filename,
            )
            # Fehler beim Storage sollte nicht die Dokumentgenerierung blockieren
            return None

    async def _render_pdf(self, html_content: str) -> bytes:
        """
        Rendert HTML zu PDF.

        Verwendet weasyprint oder alternativ ein externes Tool.
        """
        try:
            # WeasyPrint ist optionale Dependency
            from weasyprint import HTML

            pdf_bytes = HTML(string=html_content).write_pdf()
            return pdf_bytes
        except ImportError:
            logger.warning("WeasyPrint nicht verfügbar, PDF-Rendering deaktiviert")
            # Fallback: HTML als bytes zurückgeben
            return html_content.encode("utf-8")
        except Exception as e:
            logger.error(f"PDF-Rendering fehlgeschlagen: {e}")
            raise TemplateRenderError(f"PDF-Generierung fehlgeschlagen: {e}")


# Singleton-Instanz (wird in Dependencies injiziert)
_template_service: DocumentTemplateService | None = None


def get_template_service() -> DocumentTemplateService:
    """Gibt die Template-Service-Instanz zurück."""
    global _template_service
    if _template_service is None:
        raise RuntimeError("TemplateService nicht initialisiert")
    return _template_service


async def init_template_service(db: AsyncSession) -> DocumentTemplateService:
    """Initialisiert den Template-Service."""
    global _template_service
    _template_service = DocumentTemplateService(db)
    return _template_service
