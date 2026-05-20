"""Notification Template Engine - Rendering-System für Benachrichtigungsvorlagen.

Dieser Service rendert Jinja2-Templates mit Variablen und integriert
mit dem UnifiedNotificationHub.

Features:
- Sichere Jinja2-Sandbox
- Variablenvalidierung
- Vorschau-Modus
- Preset-Templates
- Integration mit UnifiedNotificationHub
"""

import uuid
from typing import Dict, List, Optional, Set
from datetime import datetime

import structlog
from jinja2 import StrictUndefined, TemplateSyntaxError
from jinja2.sandbox import SandboxedEnvironment
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_notification_template import NotificationMessageTemplate as NotificationTemplate
from app.services.notification.unified_hub import (
    UnifiedNotificationHub,
    NotificationChannel,
    NotificationSeverity,
    NotificationCategory,
    NotificationRecipient,
    NotificationPayload,
)
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# Preset-Vorlagen für häufige Benachrichtigungen
PRESET_TEMPLATES = {
    "APPROVAL_REQUESTED": {
        "name": "approval_requested",
        "category": "workflow",
        "subject": "Genehmigung angefordert: {{ document_title }}",
        "body": """Hallo {{ user_name }},

für das Dokument "{{ document_title }}" wurde eine Genehmigung angefordert.

Bitte prüfen Sie das Dokument und geben Sie Ihre Genehmigung oder Ablehnung ab.

Mit freundlichen Gruessen,
Ablage-System
""",
        "variables": {
            "required": ["user_name", "document_title"],
            "optional": [],
        },
        "channels": ["email", "in_app", "slack"],
    },
    "DOCUMENT_PROCESSED": {
        "name": "document_processed",
        "category": "document",
        "subject": "Dokument verarbeitet: {{ document_title }}",
        "body": """Hallo {{ user_name }},

das Dokument "{{ document_title }}" wurde erfolgreich verarbeitet.

Status: {{ processing_status }}
{% if ocr_confidence %}OCR-Konfidenz: {{ ocr_confidence }}%{% endif %}

Mit freundlichen Gruessen,
Ablage-System
""",
        "variables": {
            "required": ["user_name", "document_title", "processing_status"],
            "optional": ["ocr_confidence"],
        },
        "channels": ["email", "in_app"],
    },
    "ESCALATION_ALERT": {
        "name": "escalation_alert",
        "category": "alert",
        "subject": "Eskalation: {{ escalation_reason }}",
        "body": """WICHTIG: {{ user_name }}

Eine Eskalation wurde ausgeloest:

Grund: {{ escalation_reason }}
Priorität: {{ priority }}
{% if document_title %}Dokument: {{ document_title }}{% endif %}

Bitte kuemmern Sie sich umgehend um diese Angelegenheit.

Mit freundlichen Gruessen,
Ablage-System
""",
        "variables": {
            "required": ["user_name", "escalation_reason", "priority"],
            "optional": ["document_title"],
        },
        "channels": ["email", "slack", "teams", "sms"],
    },
    "PAYMENT_REMINDER": {
        "name": "payment_reminder",
        "category": "document",
        "subject": "Zahlungserinnerung: {{ invoice_number }}",
        "body": """Hallo {{ user_name }},

dies ist eine Erinnerung für die ausstehende Rechnung:

Rechnungsnummer: {{ invoice_number }}
Betrag: {{ amount }} EUR
Fälligkeitsdatum: {{ due_date }}
{% if skonto_deadline %}Skonto möglich bis: {{ skonto_deadline }} ({{ skonto_percent }}%){% endif %}

Bitte veranlassen Sie die Zahlung.

Mit freundlichen Gruessen,
Ablage-System
""",
        "variables": {
            "required": ["user_name", "invoice_number", "amount", "due_date"],
            "optional": ["skonto_deadline", "skonto_percent"],
        },
        "channels": ["email", "in_app"],
    },
    "SYSTEM_ALERT": {
        "name": "system_alert",
        "category": "system",
        "subject": "Systembenachrichtigung: {{ alert_title }}",
        "body": """Hallo {{ user_name }},

Systembenachrichtigung:

{{ alert_title }}

{{ alert_message }}

{% if action_required %}AKTION ERFORDERLICH: {{ action_required }}{% endif %}

Mit freundlichen Gruessen,
Ablage-System
""",
        "variables": {
            "required": ["user_name", "alert_title", "alert_message"],
            "optional": ["action_required"],
        },
        "channels": ["email", "in_app", "slack"],
    },
}


class NotificationTemplateEngine:
    """Template-Engine für Benachrichtigungsvorlagen.

    Rendert Jinja2-Templates sicher in einer Sandbox und validiert
    Variablen vor dem Rendering.
    """

    def __init__(self, db: AsyncSession):
        """Initialisiert die Template-Engine.

        Args:
            db: Async SQLAlchemy Session
        """
        self.db = db
        self._env = SandboxedEnvironment(
            autoescape=True,
            undefined=StrictUndefined,
        )
        self._env.filters["currency"] = self._currency_filter
        self._env.filters["date"] = self._date_filter

    @staticmethod
    def _currency_filter(value: float) -> str:
        """Formatiert Betrag als EUR-Währung."""
        return f"{value:,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", ".")

    @staticmethod
    def _date_filter(value: str) -> str:
        """Formatiert Datum im deutschen Format."""
        try:
            dt = datetime.fromisoformat(value)
            return dt.strftime("%d.%m.%Y")
        except (ValueError, AttributeError):
            return str(value)

    async def render_notification(
        self,
        template_id: uuid.UUID,
        variables: Dict[str, str],
    ) -> Dict[str, str]:
        """Rendert eine Vorlage mit Variablen.

        Args:
            template_id: UUID der Vorlage
            variables: Dict mit Variablenwerten

        Returns:
            Dict mit 'subject' und 'body'

        Raises:
            ValueError: Wenn Vorlage nicht gefunden oder Variablen fehlen
            TemplateSyntaxError: Bei Template-Syntax-Fehlern
        """
        template = await self.get_template(template_id)
        if not template:
            raise ValueError(f"Vorlage mit ID {template_id} nicht gefunden")

        if not template.is_active:
            raise ValueError(f"Vorlage '{template.name}' ist deaktiviert")

        # Variablenvalidierung
        validation = await self.validate_variables(template_id, variables)
        if not validation["valid"]:
            missing = ", ".join(validation["missing"])
            raise ValueError(f"Fehlende Variablen: {missing}")

        try:
            subject_tpl = self._env.from_string(template.subject_template)
            body_tpl = self._env.from_string(template.body_template)

            subject = subject_tpl.render(**variables)
            body = body_tpl.render(**variables)

            logger.info(
                "notification_template_rendered",
                template_id=str(template_id),
                template_name=template.name,
                variable_count=len(variables),
            )

            return {
                "subject": subject,
                "body": body,
            }

        except TemplateSyntaxError as e:
            logger.error(
                "template_syntax_error",
                template_id=str(template_id),
                error=str(e),
            )
            raise

    async def validate_variables(
        self,
        template_id: uuid.UUID,
        variables: Dict[str, str],
    ) -> Dict[str, object]:
        """Prüft ob alle erforderlichen Variablen vorhanden sind.

        Args:
            template_id: UUID der Vorlage
            variables: Dict mit Variablenwerten

        Returns:
            Dict mit 'valid' (bool) und 'missing' (List[str])
        """
        template = await self.get_template(template_id)
        if not template:
            return {"valid": False, "missing": ["template_not_found"]}

        template_vars = template.variables or {}
        required_vars: List[str] = template_vars.get("required", [])

        provided_keys: Set[str] = set(variables.keys())
        required_keys: Set[str] = set(required_vars)

        missing = list(required_keys - provided_keys)

        return {
            "valid": len(missing) == 0,
            "missing": missing,
        }

    async def preview_template(
        self,
        template_id: uuid.UUID,
        sample_data: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        """Vorschau einer Vorlage mit Beispieldaten.

        Args:
            template_id: UUID der Vorlage
            sample_data: Optionale Beispieldaten, sonst Platzhalter

        Returns:
            Dict mit 'subject' und 'body'
        """
        template = await self.get_template(template_id)
        if not template:
            raise ValueError(f"Vorlage mit ID {template_id} nicht gefunden")

        # Generiere Platzhalter für alle Variablen
        template_vars = template.variables or {}
        required_vars: List[str] = template_vars.get("required", [])
        optional_vars: List[str] = template_vars.get("optional", [])

        placeholders: Dict[str, str] = {}
        for var in required_vars + optional_vars:
            placeholders[var] = f"[{var.upper()}]"

        # Überschreibe mit sample_data falls vorhanden
        if sample_data:
            placeholders.update(sample_data)

        try:
            subject_tpl = self._env.from_string(template.subject_template)
            body_tpl = self._env.from_string(template.body_template)

            subject = subject_tpl.render(**placeholders)
            body = body_tpl.render(**placeholders)

            return {
                "subject": subject,
                "body": body,
            }

        except TemplateSyntaxError as e:
            logger.error(
                "preview_template_syntax_error",
                template_id=str(template_id),
                error=str(e),
            )
            raise

    async def get_template(
        self,
        template_id: uuid.UUID,
    ) -> Optional[NotificationTemplate]:
        """Holt eine Vorlage anhand der ID.

        Args:
            template_id: UUID der Vorlage

        Returns:
            NotificationTemplate oder None
        """
        stmt = select(NotificationTemplate).where(
            NotificationTemplate.id == template_id
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_templates(
        self,
        category: Optional[str] = None,
        active_only: bool = True,
    ) -> List[NotificationTemplate]:
        """Listet alle Vorlagen auf, optional nach Kategorie gefiltert.

        Args:
            category: Optionale Kategoriefilterung
            active_only: Nur aktive Vorlagen

        Returns:
            Liste von NotificationTemplate
        """
        stmt = select(NotificationTemplate)

        if active_only:
            stmt = stmt.where(NotificationTemplate.is_active == True)

        if category:
            stmt = stmt.where(NotificationTemplate.category == category)

        stmt = stmt.order_by(NotificationTemplate.name)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create_template(
        self,
        name: str,
        category: str,
        subject_template: str,
        body_template: str,
        variables: Optional[Dict[str, List[str]]] = None,
        channels: Optional[List[str]] = None,
        created_by_id: Optional[uuid.UUID] = None,
    ) -> NotificationTemplate:
        """Erstellt eine neue Vorlage.

        Args:
            name: Eindeutiger Name
            category: Kategorie
            subject_template: Jinja2-Template für Betreff
            body_template: Jinja2-Template für Body
            variables: Dict mit 'required' und 'optional' Listen
            channels: Liste unterstützter Channels
            created_by_id: Ersteller-User-ID

        Returns:
            Erstellte NotificationTemplate
        """
        # Validiere Template-Syntax
        try:
            self._env.from_string(subject_template)
            self._env.from_string(body_template)
        except TemplateSyntaxError as e:
            logger.error("invalid_template_syntax", error=str(e))
            raise ValueError(f"Template-Syntax-Fehler: {e}")

        template = NotificationTemplate(
            name=name,
            category=category,
            subject_template=subject_template,
            body_template=body_template,
            variables=variables,
            channels=channels,
            created_by_id=created_by_id,
        )

        self.db.add(template)
        await self.db.commit()
        await self.db.refresh(template)

        logger.info(
            "notification_template_created",
            template_id=str(template.id),
            template_name=name,
        )

        return template

    async def update_template(
        self,
        template_id: uuid.UUID,
        name: Optional[str] = None,
        category: Optional[str] = None,
        subject_template: Optional[str] = None,
        body_template: Optional[str] = None,
        variables: Optional[Dict[str, List[str]]] = None,
        channels: Optional[List[str]] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[NotificationTemplate]:
        """Aktualisiert eine bestehende Vorlage.

        Args:
            template_id: UUID der Vorlage
            name: Neuer Name (optional)
            category: Neue Kategorie (optional)
            subject_template: Neues Subject-Template (optional)
            body_template: Neues Body-Template (optional)
            variables: Neue Variablen (optional)
            channels: Neue Channels (optional)
            is_active: Neuer Aktiv-Status (optional)

        Returns:
            Aktualisierte NotificationTemplate oder None
        """
        template = await self.get_template(template_id)
        if not template:
            return None

        # Validiere Template-Syntax wenn geändert
        if subject_template is not None:
            try:
                self._env.from_string(subject_template)
            except TemplateSyntaxError as e:
                raise ValueError(f"Subject-Template-Syntax-Fehler: {e}")
            template.subject_template = subject_template

        if body_template is not None:
            try:
                self._env.from_string(body_template)
            except TemplateSyntaxError as e:
                raise ValueError(f"Body-Template-Syntax-Fehler: {e}")
            template.body_template = body_template

        if name is not None:
            template.name = name
        if category is not None:
            template.category = category
        if variables is not None:
            template.variables = variables
        if channels is not None:
            template.channels = channels
        if is_active is not None:
            template.is_active = is_active

        await self.db.commit()
        await self.db.refresh(template)

        logger.info(
            "notification_template_updated",
            template_id=str(template_id),
        )

        return template

    async def delete_template(
        self,
        template_id: uuid.UUID,
    ) -> bool:
        """Löscht eine Vorlage (Soft-Delete via is_active=False).

        Args:
            template_id: UUID der Vorlage

        Returns:
            True wenn erfolgreich, False wenn nicht gefunden
        """
        template = await self.get_template(template_id)
        if not template:
            return False

        template.is_active = False
        await self.db.commit()

        logger.info(
            "notification_template_deleted",
            template_id=str(template_id),
        )

        return True

    async def send_with_template(
        self,
        template_id: uuid.UUID,
        variables: Dict[str, str],
        recipient_id: uuid.UUID,
        channels: Optional[List[str]] = None,
        severity: str = "info",
    ) -> Dict[str, object]:
        """Rendert Vorlage und sendet über UnifiedNotificationHub.

        Args:
            template_id: UUID der Vorlage
            variables: Dict mit Variablenwerten
            recipient_id: Empfänger-User-ID
            channels: Optionale Channel-Überschreibung
            severity: Severity-Level (info, low, medium, high, critical)

        Returns:
            Dict mit 'success', 'message', 'results'
        """
        template = await self.get_template(template_id)
        if not template:
            return {
                "success": False,
                "message": "Vorlage nicht gefunden",
                "results": {},
            }

        # Rendere Template
        try:
            rendered = await self.render_notification(template_id, variables)
        except (ValueError, TemplateSyntaxError) as e:
            return {
                "success": False,
                "message": f"Rendering fehlgeschlagen: {e}",
                "results": {},
            }

        # Bestimme Channels
        target_channels = channels or template.channels or ["email", "in_app"]

        # Sende über UnifiedNotificationHub
        hub = UnifiedNotificationHub(self.db)

        try:
            sev = NotificationSeverity(severity)
            cat = NotificationCategory(template.category)
        except (ValueError, TypeError) as e:
            return {
                "success": False,
                "message": "Ungültiger Severity- oder Kategorie-Wert",
                "results": {},
            }

        recipient = NotificationRecipient(
            user_id=recipient_id,
        )
        payload = NotificationPayload(
            notification_type=f"template_{template.name}",
            title=rendered["subject"],
            message=rendered["body"],
            category=cat,
            severity=sev,
        )

        results: Dict[str, bool] = {}
        for channel_name in target_channels:
            try:
                channel = NotificationChannel(channel_name)
                delivery_results = await hub.send(
                    recipients=[recipient],
                    payload=payload,
                    channels=[channel],
                )
                results[channel_name] = (
                    len(delivery_results) > 0
                    and delivery_results[0].success
                )

            except Exception as e:
                logger.error("channel_send_failed", **safe_error_log(e), channel=channel_name)
                results[channel_name] = False

        success_count = sum(1 for v in results.values() if v)
        total_count = len(results)

        return {
            "success": success_count > 0,
            "message": f"{success_count}/{total_count} Channels erfolgreich",
            "results": results,
        }


def get_template_engine(db: AsyncSession) -> NotificationTemplateEngine:
    """Factory-Funktion für NotificationTemplateEngine.

    Args:
        db: Async SQLAlchemy Session

    Returns:
        NotificationTemplateEngine-Instanz
    """
    return NotificationTemplateEngine(db)
