"""
Workflow Templates

Vordefinierte Workflow-Templates fuer haeufige Anwendungsfaelle.
Diese werden beim ersten Start oder via Admin-API erstellt.
"""

from typing import List, Dict, Any
from uuid import UUID

PREBUILT_TEMPLATES: List[Dict[str, Any]] = [
    # ==========================================================================
    # Template 1: Auto-Kategorisierung
    # ==========================================================================
    {
        "name": "Auto-Kategorisierung",
        "description": "Automatische KI-Kategorisierung neuer Dokumente mit Benachrichtigung bei niedriger Konfidenz.",
        "trigger_type": "document_event",
        "trigger_config": {
            "events": ["created"],
            "category": "ai",
            "scope": "global",
            "allow_manual_trigger": True,
        },
        "nodes": [
            {
                "id": "trigger-1",
                "type": "trigger",
                "position": {"x": 250, "y": 50},
                "data": {
                    "label": "Neues Dokument",
                    "triggerType": "document_event",
                    "config": {"events": ["created"]},
                    "isActive": True,
                },
            },
            {
                "id": "action-categorize",
                "type": "action",
                "position": {"x": 250, "y": 150},
                "data": {
                    "label": "KI-Kategorisierung",
                    "config": {"action_type": "ai_categorization"},
                    "stepName": "Dokument kategorisieren",
                },
            },
            {
                "id": "condition-confidence",
                "type": "condition",
                "position": {"x": 250, "y": 250},
                "data": {
                    "label": "Konfidenz pruefen",
                    "config": {
                        "conditions": {
                            "operator": "AND",
                            "rules": [
                                {"field": "ocr_confidence", "operator": "less_than", "value": 70}
                            ],
                        }
                    },
                },
            },
            {
                "id": "action-notify",
                "type": "action",
                "position": {"x": 100, "y": 350},
                "data": {
                    "label": "Benachrichtigung",
                    "config": {
                        "action_type": "send_notification",
                        "title": "Manuelle Pruefung erforderlich",
                        "message": "Dokument mit niedriger Konfidenz: {{document.original_filename}}",
                    },
                    "stepName": "Admin benachrichtigen",
                },
            },
            {
                "id": "action-log",
                "type": "action",
                "position": {"x": 400, "y": 350},
                "data": {
                    "label": "Log",
                    "config": {
                        "action_type": "log_message",
                        "message": "Dokument erfolgreich kategorisiert",
                        "level": "info",
                    },
                    "stepName": "Erfolg loggen",
                },
            },
        ],
        "edges": [
            {"id": "e1", "source": "trigger-1", "target": "action-categorize"},
            {"id": "e2", "source": "action-categorize", "target": "condition-confidence"},
            {"id": "e3", "source": "condition-confidence", "target": "action-notify", "sourceHandle": "true"},
            {"id": "e4", "source": "condition-confidence", "target": "action-log", "sourceHandle": "false"},
        ],
        "variables": {},
        "is_template": True,
        "max_concurrent_executions": 10,
        "timeout_seconds": 300,
        "retry_config": {"max_retries": 2, "retry_delay": 60, "exponential_backoff": True},
    },

    # ==========================================================================
    # Template 2: Rechnungsverarbeitung
    # ==========================================================================
    {
        "name": "Rechnungsverarbeitung",
        "description": "OCR und Extraktion fuer Rechnungen mit Pruefung bei hohen Betraegen.",
        "trigger_type": "document_event",
        "trigger_config": {
            "events": ["created"],
            "document_types": ["invoice"],
            "category": "document",
            "scope": "global",
            "allow_manual_trigger": True,
        },
        "nodes": [
            {
                "id": "trigger-1",
                "type": "trigger",
                "position": {"x": 250, "y": 50},
                "data": {
                    "label": "Neue Rechnung",
                    "triggerType": "document_event",
                    "config": {"events": ["created"], "document_types": ["invoice"]},
                    "isActive": True,
                },
            },
            {
                "id": "action-ocr",
                "type": "action",
                "position": {"x": 250, "y": 150},
                "data": {
                    "label": "OCR starten",
                    "config": {"action_type": "start_ocr", "backend": "auto", "priority": "high"},
                    "stepName": "OCR-Verarbeitung",
                },
            },
            {
                "id": "delay-1",
                "type": "delay",
                "position": {"x": 250, "y": 250},
                "data": {
                    "label": "Warten auf OCR",
                    "config": {"delay_seconds": 30},
                    "stepName": "OCR-Verarbeitung abwarten",
                },
            },
            {
                "id": "condition-amount",
                "type": "condition",
                "position": {"x": 250, "y": 350},
                "data": {
                    "label": "Betrag pruefen",
                    "config": {
                        "conditions": {
                            "operator": "AND",
                            "rules": [
                                {"field": "extracted_data.total_gross", "operator": "greater_than", "value": 10000}
                            ],
                        }
                    },
                    "stepName": "Hoher Betrag?",
                },
            },
            {
                "id": "action-approval",
                "type": "action",
                "position": {"x": 100, "y": 450},
                "data": {
                    "label": "Genehmigung anfordern",
                    "config": {
                        "action_type": "request_approval",
                        "title": "Rechnung ueber 10.000 EUR",
                        "message": "Bitte pruefen: {{document.original_filename}} - Betrag: {{extracted_data.total_gross}} EUR",
                    },
                    "stepName": "Genehmigung einholen",
                },
            },
            {
                "id": "action-tag",
                "type": "action",
                "position": {"x": 400, "y": 450},
                "data": {
                    "label": "Tags zuweisen",
                    "config": {
                        "action_type": "assign_tags",
                        "tag_names": ["verarbeitet", "geprueft"],
                    },
                    "stepName": "Als verarbeitet markieren",
                },
            },
        ],
        "edges": [
            {"id": "e1", "source": "trigger-1", "target": "action-ocr"},
            {"id": "e2", "source": "action-ocr", "target": "delay-1"},
            {"id": "e3", "source": "delay-1", "target": "condition-amount"},
            {"id": "e4", "source": "condition-amount", "target": "action-approval", "sourceHandle": "true"},
            {"id": "e5", "source": "condition-amount", "target": "action-tag", "sourceHandle": "false"},
            {"id": "e6", "source": "action-approval", "target": "action-tag"},
        ],
        "variables": {},
        "is_template": True,
        "max_concurrent_executions": 5,
        "timeout_seconds": 600,
        "retry_config": {"max_retries": 3, "retry_delay": 120, "exponential_backoff": True},
    },

    # ==========================================================================
    # Template 3: Woechentlicher Bericht
    # ==========================================================================
    {
        "name": "Woechentlicher Bericht",
        "description": "Automatischer woechentlicher Bericht mit E-Mail-Versand jeden Montag.",
        "trigger_type": "schedule",
        "trigger_config": {
            "cron": "0 8 * * 1",  # Jeden Montag um 08:00
            "timezone": "Europe/Berlin",
            "category": "schedule",
            "scope": "global",
            "allow_manual_trigger": True,
        },
        "nodes": [
            {
                "id": "trigger-1",
                "type": "trigger",
                "position": {"x": 250, "y": 50},
                "data": {
                    "label": "Montag 08:00",
                    "triggerType": "schedule",
                    "config": {"cron": "0 8 * * 1", "timezone": "Europe/Berlin"},
                    "isActive": True,
                },
            },
            {
                "id": "action-variable",
                "type": "action",
                "position": {"x": 250, "y": 150},
                "data": {
                    "label": "Zeitraum setzen",
                    "config": {
                        "action_type": "set_variable",
                        "name": "report_period",
                        "value": "last_7_days",
                    },
                    "stepName": "Berichtszeitraum definieren",
                },
            },
            {
                "id": "action-webhook",
                "type": "action",
                "position": {"x": 250, "y": 250},
                "data": {
                    "label": "Bericht generieren",
                    "config": {
                        "action_type": "http_request",
                        "method": "POST",
                        "url": "/api/v1/reports/templates/weekly-summary/execute",
                        "headers": {"Content-Type": "application/json"},
                        "body": {"period": "{{report_period}}"},
                    },
                    "stepName": "Report-API aufrufen",
                },
            },
            {
                "id": "action-email",
                "type": "action",
                "position": {"x": 250, "y": 350},
                "data": {
                    "label": "E-Mail senden",
                    "config": {
                        "action_type": "send_email",
                        "subject": "Woechentlicher Dokumenten-Report",
                        "template": "weekly_report",
                    },
                    "stepName": "Report per E-Mail versenden",
                },
            },
            {
                "id": "action-notify",
                "type": "action",
                "position": {"x": 250, "y": 450},
                "data": {
                    "label": "Benachrichtigung",
                    "config": {
                        "action_type": "send_notification",
                        "title": "Woechentlicher Bericht erstellt",
                        "message": "Der Bericht wurde erfolgreich generiert und versendet.",
                    },
                    "stepName": "Erfolg melden",
                },
            },
        ],
        "edges": [
            {"id": "e1", "source": "trigger-1", "target": "action-variable"},
            {"id": "e2", "source": "action-variable", "target": "action-webhook"},
            {"id": "e3", "source": "action-webhook", "target": "action-email"},
            {"id": "e4", "source": "action-email", "target": "action-notify"},
        ],
        "variables": {"report_period": "last_7_days"},
        "is_template": True,
        "max_concurrent_executions": 1,
        "timeout_seconds": 900,
        "retry_config": {"max_retries": 2, "retry_delay": 300, "exponential_backoff": False},
    },

    # ==========================================================================
    # Template 4: Duplikat-Erkennung
    # ==========================================================================
    {
        "name": "Duplikat-Erkennung",
        "description": "Automatische Pruefung auf Duplikate bei neuen Dokumenten mit Archivierung.",
        "trigger_type": "document_event",
        "trigger_config": {
            "events": ["created"],
            "category": "document",
            "scope": "global",
            "allow_manual_trigger": True,
        },
        "nodes": [
            {
                "id": "trigger-1",
                "type": "trigger",
                "position": {"x": 250, "y": 50},
                "data": {
                    "label": "Neues Dokument",
                    "triggerType": "document_event",
                    "config": {"events": ["created"]},
                    "isActive": True,
                },
            },
            {
                "id": "action-duplicate",
                "type": "action",
                "position": {"x": 250, "y": 150},
                "data": {
                    "label": "Duplikat-Check",
                    "config": {"action_type": "duplicate_check"},
                    "stepName": "Duplikate suchen",
                },
            },
            {
                "id": "condition-duplicate",
                "type": "condition",
                "position": {"x": 250, "y": 250},
                "data": {
                    "label": "Duplikat gefunden?",
                    "config": {
                        "conditions": {
                            "operator": "AND",
                            "rules": [
                                {"field": "duplicate_found", "operator": "is_true", "value": None}
                            ],
                        }
                    },
                },
            },
            {
                "id": "action-move-archive",
                "type": "action",
                "position": {"x": 100, "y": 350},
                "data": {
                    "label": "Archivieren",
                    "config": {
                        "action_type": "move_folder",
                        "folder_id": "duplicates-archive",
                    },
                    "stepName": "In Duplikat-Ordner verschieben",
                },
            },
            {
                "id": "action-notify-duplicate",
                "type": "action",
                "position": {"x": 100, "y": 450},
                "data": {
                    "label": "Hinweis",
                    "config": {
                        "action_type": "send_notification",
                        "title": "Duplikat erkannt",
                        "message": "Das Dokument {{document.original_filename}} wurde als Duplikat erkannt.",
                    },
                    "stepName": "User informieren",
                },
            },
            {
                "id": "action-tag-new",
                "type": "action",
                "position": {"x": 400, "y": 350},
                "data": {
                    "label": "Als neu markieren",
                    "config": {
                        "action_type": "assign_tags",
                        "tag_names": ["neu", "einzigartig"],
                    },
                    "stepName": "Tags zuweisen",
                },
            },
        ],
        "edges": [
            {"id": "e1", "source": "trigger-1", "target": "action-duplicate"},
            {"id": "e2", "source": "action-duplicate", "target": "condition-duplicate"},
            {"id": "e3", "source": "condition-duplicate", "target": "action-move-archive", "sourceHandle": "true"},
            {"id": "e4", "source": "action-move-archive", "target": "action-notify-duplicate"},
            {"id": "e5", "source": "condition-duplicate", "target": "action-tag-new", "sourceHandle": "false"},
        ],
        "variables": {},
        "is_template": True,
        "max_concurrent_executions": 10,
        "timeout_seconds": 300,
        "retry_config": {"max_retries": 1, "retry_delay": 30, "exponential_backoff": False},
    },

    # ==========================================================================
    # Template 5: Genehmigungsworkflow
    # ==========================================================================
    {
        "name": "Genehmigungsworkflow",
        "description": "Dokument zur Genehmigung zuweisen und auf Freigabe warten.",
        "trigger_type": "manual",
        "trigger_config": {
            "category": "approval",
            "scope": "user",
            "allow_manual_trigger": True,
        },
        "nodes": [
            {
                "id": "trigger-1",
                "type": "trigger",
                "position": {"x": 250, "y": 50},
                "data": {
                    "label": "Manuell starten",
                    "triggerType": "manual",
                    "config": {},
                    "isActive": True,
                },
            },
            {
                "id": "action-assign",
                "type": "action",
                "position": {"x": 250, "y": 150},
                "data": {
                    "label": "Bearbeiter zuweisen",
                    "config": {
                        "action_type": "assign_user",
                        "user_id": "{{variables.approver_id}}",
                    },
                    "stepName": "Genehmiger zuweisen",
                },
            },
            {
                "id": "action-status",
                "type": "action",
                "position": {"x": 250, "y": 250},
                "data": {
                    "label": "Status aendern",
                    "config": {
                        "action_type": "update_status",
                        "status": "pending_approval",
                    },
                    "stepName": "Auf Genehmigung wartend",
                },
            },
            {
                "id": "action-notify-approver",
                "type": "action",
                "position": {"x": 250, "y": 350},
                "data": {
                    "label": "Genehmiger benachrichtigen",
                    "config": {
                        "action_type": "send_notification",
                        "title": "Genehmigung erforderlich",
                        "message": "Bitte pruefen Sie: {{document.original_filename}}",
                        "user_ids": ["{{variables.approver_id}}"],
                    },
                    "stepName": "Benachrichtigung senden",
                },
            },
            {
                "id": "action-task",
                "type": "action",
                "position": {"x": 250, "y": 450},
                "data": {
                    "label": "Aufgabe erstellen",
                    "config": {
                        "action_type": "create_task",
                        "title": "Dokument genehmigen",
                        "assignee_id": "{{variables.approver_id}}",
                        "due_date": "+3d",
                    },
                    "stepName": "Aufgabe anlegen",
                },
            },
        ],
        "edges": [
            {"id": "e1", "source": "trigger-1", "target": "action-assign"},
            {"id": "e2", "source": "action-assign", "target": "action-status"},
            {"id": "e3", "source": "action-status", "target": "action-notify-approver"},
            {"id": "e4", "source": "action-notify-approver", "target": "action-task"},
        ],
        "variables": {"approver_id": ""},
        "is_template": True,
        "max_concurrent_executions": 20,
        "timeout_seconds": 86400,  # 24 Stunden
        "retry_config": {"max_retries": 0, "retry_delay": 0, "exponential_backoff": False},
    },
]


async def seed_workflow_templates(db_session) -> int:
    """
    Erstellt die vordefinierten Workflow-Templates in der Datenbank.

    Returns:
        Anzahl der erstellten Templates
    """
    from app.services.workflow import WorkflowService
    from uuid import uuid4

    service = WorkflowService()
    created_count = 0

    for template_data in PREBUILT_TEMPLATES:
        # Pruefe ob Template bereits existiert
        existing = await service.list_templates(
            db=db_session,
            category=template_data.get("trigger_config", {}).get("category")
        )

        template_exists = any(t.name == template_data["name"] for t in existing)

        if not template_exists:
            # System-User als Owner (oder ersten Admin)
            from sqlalchemy import select
            from app.db.models import User

            admin_result = await db_session.execute(
                select(User).where(User.role == "admin").limit(1)
            )
            admin_user = admin_result.scalar_one_or_none()

            if admin_user:
                from app.services.workflow.workflow_service import WorkflowCreate

                create_data = WorkflowCreate(
                    name=template_data["name"],
                    description=template_data["description"],
                    trigger_type=template_data["trigger_type"],
                    trigger_config=template_data["trigger_config"],
                    nodes=template_data["nodes"],
                    edges=template_data["edges"],
                    variables=template_data.get("variables", {}),
                    max_concurrent_executions=template_data.get("max_concurrent_executions", 10),
                    timeout_seconds=template_data.get("timeout_seconds", 3600),
                    retry_config=template_data.get("retry_config"),
                )

                workflow = await service.create_workflow(
                    db=db_session,
                    user_id=admin_user.id,
                    data=create_data,
                    is_template=True
                )

                if workflow:
                    created_count += 1

    return created_count
