"""Enterprise BPMN Workflow Templates.

Vordefinierte Workflow-Templates für typische Geschäftsprozesse:
- Rechnungsfreigabe mit Betrags-Eskalation
- Automatisches Mahnwesen
- Kunden-Onboarding
- Dokumenten-Klassifizierung

Diese Templates können direkt deployed oder als Basis für eigene Workflows genutzt werden.
"""

from typing import Dict, Any, List
from enum import Enum


class WorkflowCategory(str, Enum):
    """Workflow-Kategorien."""
    FINANZEN = "Finanzen"
    KUNDEN = "Kunden"
    DOKUMENTE = "Dokumente"
    HR = "HR"
    EINKAUF = "Einkauf"


# =============================================================================
# WORKFLOW TEMPLATE: Rechnungsfreigabe (Invoice Approval)
# =============================================================================

INVOICE_APPROVAL_WORKFLOW: Dict[str, Any] = {
    "key": "invoice-approval",
    "name": "Rechnungsfreigabe",
    "description": """
Mehrstufiger Freigabe-Workflow für eingehende Rechnungen.

Ablauf:
1. Rechnung wird eingereicht (automatisch nach OCR oder manuell)
2. Sachbearbeiter prüft Rechnung (Formelle Prüfung)
3. Bei Betrag > 1.000 EUR: Abteilungsleiter-Freigabe erforderlich
4. Bei Betrag > 5.000 EUR: Zusätzlich Geschäftsführer-Freigabe
5. Nach Freigabe: Buchung und Zahlung ausloesen

Features:
- Automatische Eskalation bei Überfälligkeit (24h, 48h, 72h)
- Betrags-basiertes Routing
- Audit-Trail für alle Entscheidungen
- Integration mit Banking-Modul für Zahlungsausloesung
""",
    "category": WorkflowCategory.FINANZEN,
    "tags": ["rechnung", "freigabe", "approval", "finanzen"],
    "process_data": {
        "id": "invoice-approval",
        "name": "Rechnungsfreigabe",
        "is_executable": True,
        "elements": [
            # Start Event
            {
                "id": "start_invoice",
                "type": "startEvent",
                "name": "Rechnung eingegangen",
                "outgoing": ["flow_to_check"],
            },
            # Task 1: Formelle Prüfung
            {
                "id": "task_formal_check",
                "type": "userTask",
                "name": "Formelle Prüfung",
                "incoming": ["flow_to_check"],
                "outgoing": ["flow_to_gateway_amount"],
                "assignee_group": "Buchhaltung",
                "form_key": "form:invoice-check",
                "extension_properties": {
                    "description": "Prüfen Sie die Rechnung auf Vollständigkeit und Korrektheit",
                    "required_fields": ["supplier_valid", "amount_correct", "tax_correct"],
                },
            },
            # Gateway: Betrags-Prüfung
            {
                "id": "gateway_amount",
                "type": "exclusiveGateway",
                "name": "Betrag prüfen",
                "incoming": ["flow_to_gateway_amount"],
                "outgoing": ["flow_small_amount", "flow_medium_amount", "flow_large_amount"],
            },
            # Branch 1: Kleine Betraege (< 1000 EUR) - Direkt freigeben
            {
                "id": "task_auto_approve",
                "type": "serviceTask",
                "name": "Automatische Freigabe",
                "incoming": ["flow_small_amount"],
                "outgoing": ["flow_to_booking"],
                "implementation": "python:app.services.bpmn.invoice_tasks.auto_approve_invoice",
            },
            # Branch 2: Mittlere Betraege (1000-5000 EUR) - Abteilungsleiter
            {
                "id": "task_dept_approval",
                "type": "userTask",
                "name": "Abteilungsleiter-Freigabe",
                "incoming": ["flow_medium_amount"],
                "outgoing": ["flow_dept_to_gateway"],
                "assignee_group": "Abteilungsleiter",
                "form_key": "form:invoice-approval",
                "due_date_duration": "PT24H",
                "extension_properties": {
                    "escalation_after": "PT48H",
                    "escalation_to": "Geschäftsführung",
                },
            },
            # Gateway nach Abteilungsleiter
            {
                "id": "gateway_dept_decision",
                "type": "exclusiveGateway",
                "name": "Entscheidung Abteilungsleiter",
                "incoming": ["flow_dept_to_gateway"],
                "outgoing": ["flow_dept_approved", "flow_dept_rejected"],
            },
            # Branch 3: Grosse Betraege (> 5000 EUR) - Geschäftsführer
            {
                "id": "task_ceo_approval",
                "type": "userTask",
                "name": "Geschäftsführer-Freigabe",
                "incoming": ["flow_large_amount", "flow_dept_approved_large"],
                "outgoing": ["flow_ceo_to_gateway"],
                "assignee_group": "Geschäftsführung",
                "form_key": "form:invoice-approval-ceo",
                "due_date_duration": "PT48H",
                "extension_properties": {
                    "priority": 80,
                    "notify_slack": True,
                },
            },
            # Gateway nach Geschäftsführer
            {
                "id": "gateway_ceo_decision",
                "type": "exclusiveGateway",
                "name": "Entscheidung Geschäftsführer",
                "incoming": ["flow_ceo_to_gateway"],
                "outgoing": ["flow_ceo_approved", "flow_ceo_rejected"],
            },
            # Task: Buchung
            {
                "id": "task_booking",
                "type": "serviceTask",
                "name": "Rechnung buchen",
                "incoming": ["flow_to_booking", "flow_dept_approved", "flow_ceo_approved"],
                "outgoing": ["flow_to_payment"],
                "implementation": "python:app.services.bpmn.invoice_tasks.book_invoice",
            },
            # Task: Zahlung ausloesen
            {
                "id": "task_payment",
                "type": "serviceTask",
                "name": "Zahlung ausloesen",
                "incoming": ["flow_to_payment"],
                "outgoing": ["flow_to_end_success"],
                "implementation": "celery:banking.create_sepa_transfer",
            },
            # Task: Ablehnung bearbeiten
            {
                "id": "task_rejection",
                "type": "userTask",
                "name": "Ablehnung bearbeiten",
                "incoming": ["flow_dept_rejected", "flow_ceo_rejected"],
                "outgoing": ["flow_to_end_rejected"],
                "assignee_group": "Buchhaltung",
                "form_key": "form:invoice-rejection",
            },
            # End Events
            {
                "id": "end_success",
                "type": "endEvent",
                "name": "Rechnung bezahlt",
                "incoming": ["flow_to_end_success"],
            },
            {
                "id": "end_rejected",
                "type": "endEvent",
                "name": "Rechnung abgelehnt",
                "incoming": ["flow_to_end_rejected"],
            },
            # Sequence Flows
            {
                "id": "flow_to_check",
                "type": "sequenceFlow",
                "source_ref": "start_invoice",
                "target_ref": "task_formal_check",
            },
            {
                "id": "flow_to_gateway_amount",
                "type": "sequenceFlow",
                "source_ref": "task_formal_check",
                "target_ref": "gateway_amount",
            },
            {
                "id": "flow_small_amount",
                "type": "sequenceFlow",
                "source_ref": "gateway_amount",
                "target_ref": "task_auto_approve",
                "condition": "${amount < 1000}",
                "name": "< 1.000 EUR",
            },
            {
                "id": "flow_medium_amount",
                "type": "sequenceFlow",
                "source_ref": "gateway_amount",
                "target_ref": "task_dept_approval",
                "condition": "${amount >= 1000 && amount < 5000}",
                "name": "1.000 - 5.000 EUR",
            },
            {
                "id": "flow_large_amount",
                "type": "sequenceFlow",
                "source_ref": "gateway_amount",
                "target_ref": "task_ceo_approval",
                "condition": "${amount >= 5000}",
                "name": ">= 5.000 EUR",
            },
            {
                "id": "flow_dept_to_gateway",
                "type": "sequenceFlow",
                "source_ref": "task_dept_approval",
                "target_ref": "gateway_dept_decision",
            },
            {
                "id": "flow_dept_approved",
                "type": "sequenceFlow",
                "source_ref": "gateway_dept_decision",
                "target_ref": "task_booking",
                "condition": "${approved == true && amount < 5000}",
                "name": "Genehmigt",
            },
            {
                "id": "flow_dept_approved_large",
                "type": "sequenceFlow",
                "source_ref": "gateway_dept_decision",
                "target_ref": "task_ceo_approval",
                "condition": "${approved == true && amount >= 5000}",
                "name": "Weiter zu GF",
            },
            {
                "id": "flow_dept_rejected",
                "type": "sequenceFlow",
                "source_ref": "gateway_dept_decision",
                "target_ref": "task_rejection",
                "condition": "${approved == false}",
                "name": "Abgelehnt",
            },
            {
                "id": "flow_ceo_to_gateway",
                "type": "sequenceFlow",
                "source_ref": "task_ceo_approval",
                "target_ref": "gateway_ceo_decision",
            },
            {
                "id": "flow_ceo_approved",
                "type": "sequenceFlow",
                "source_ref": "gateway_ceo_decision",
                "target_ref": "task_booking",
                "condition": "${approved == true}",
                "name": "Genehmigt",
            },
            {
                "id": "flow_ceo_rejected",
                "type": "sequenceFlow",
                "source_ref": "gateway_ceo_decision",
                "target_ref": "task_rejection",
                "condition": "${approved == false}",
                "name": "Abgelehnt",
            },
            {
                "id": "flow_to_booking",
                "type": "sequenceFlow",
                "source_ref": "task_auto_approve",
                "target_ref": "task_booking",
            },
            {
                "id": "flow_to_payment",
                "type": "sequenceFlow",
                "source_ref": "task_booking",
                "target_ref": "task_payment",
            },
            {
                "id": "flow_to_end_success",
                "type": "sequenceFlow",
                "source_ref": "task_payment",
                "target_ref": "end_success",
            },
            {
                "id": "flow_to_end_rejected",
                "type": "sequenceFlow",
                "source_ref": "task_rejection",
                "target_ref": "end_rejected",
            },
        ],
    },
    "variables_schema": {
        "invoice_id": {"type": "string", "required": True, "description": "Rechnungs-ID"},
        "document_id": {"type": "string", "required": True, "description": "Dokument-ID"},
        "supplier_id": {"type": "string", "required": False, "description": "Lieferanten-ID"},
        "amount": {"type": "number", "required": True, "description": "Rechnungsbetrag"},
        "currency": {"type": "string", "default": "EUR", "description": "Währung"},
        "due_date": {"type": "date", "required": False, "description": "Fälligkeitsdatum"},
        "approved": {"type": "boolean", "description": "Freigabe-Entscheidung"},
        "rejection_reason": {"type": "string", "description": "Ablehnungsgrund"},
    },
}


# =============================================================================
# WORKFLOW TEMPLATE: Automatisches Mahnwesen (Dunning Process)
# =============================================================================

DUNNING_PROCESS_WORKFLOW: Dict[str, Any] = {
    "key": "dunning-process",
    "name": "Automatisches Mahnwesen",
    "description": """
Automatisierter Mahnprozess für überfällige Rechnungen.

Ablauf:
1. Rechnung wird überfällig (Trigger: Timer oder manuell)
2. Zahlungserinnerung (freundlich, keine Gebühren)
3. Erste Mahnung nach 14 Tagen (Mahngebühr möglich)
4. Zweite Mahnung nach weiteren 14 Tagen (höhere Gebühr)
5. Dritte Mahnung nach weiteren 14 Tagen (letzte Warnung)
6. Inkasso-Übergabe oder Abschreibung

Features:
- Automatische Timer-Events
- Eskalationsstufen mit konfigurierbaren Intervallen
- Integration mit Telefon-Protokoll
- Optionale Inkasso-Übergabe
""",
    "category": WorkflowCategory.FINANZEN,
    "tags": ["mahnung", "inkasso", "forderungen", "dunning"],
    "process_data": {
        "id": "dunning-process",
        "name": "Automatisches Mahnwesen",
        "is_executable": True,
        "elements": [
            # Start Event
            {
                "id": "start_dunning",
                "type": "startEvent",
                "name": "Rechnung überfällig",
                "outgoing": ["flow_to_reminder"],
            },
            # Task 1: Zahlungserinnerung senden
            {
                "id": "task_send_reminder",
                "type": "serviceTask",
                "name": "Zahlungserinnerung senden",
                "incoming": ["flow_to_reminder"],
                "outgoing": ["flow_reminder_to_timer"],
                "implementation": "celery:dunning.send_payment_reminder",
            },
            # Timer: 14 Tage warten
            {
                "id": "timer_14_days_1",
                "type": "intermediateCatchEvent",
                "name": "14 Tage warten",
                "incoming": ["flow_reminder_to_timer"],
                "outgoing": ["flow_timer_to_check_1"],
                "timer_type": "duration",
                "timer_value": "P14D",
            },
            # Gateway: Zahlung eingegangen?
            {
                "id": "gateway_payment_check_1",
                "type": "exclusiveGateway",
                "name": "Zahlung eingegangen?",
                "incoming": ["flow_timer_to_check_1"],
                "outgoing": ["flow_paid_1", "flow_unpaid_1"],
            },
            # Task 2: Erste Mahnung
            {
                "id": "task_first_dunning",
                "type": "serviceTask",
                "name": "1. Mahnung senden",
                "incoming": ["flow_unpaid_1"],
                "outgoing": ["flow_to_timer_2"],
                "implementation": "celery:dunning.send_first_dunning",
            },
            # Optional: Telefonat
            {
                "id": "task_phone_call_1",
                "type": "userTask",
                "name": "Telefonische Nachfrage",
                "incoming": ["flow_to_phone_1"],
                "outgoing": ["flow_phone_to_timer_2"],
                "assignee_group": "Buchhaltung",
                "form_key": "form:phone-protocol",
            },
            # Timer: 14 Tage warten
            {
                "id": "timer_14_days_2",
                "type": "intermediateCatchEvent",
                "name": "14 Tage warten",
                "incoming": ["flow_to_timer_2", "flow_phone_to_timer_2"],
                "outgoing": ["flow_timer_to_check_2"],
                "timer_type": "duration",
                "timer_value": "P14D",
            },
            # Gateway: Zahlung eingegangen?
            {
                "id": "gateway_payment_check_2",
                "type": "exclusiveGateway",
                "name": "Zahlung eingegangen?",
                "incoming": ["flow_timer_to_check_2"],
                "outgoing": ["flow_paid_2", "flow_unpaid_2"],
            },
            # Task 3: Zweite Mahnung
            {
                "id": "task_second_dunning",
                "type": "serviceTask",
                "name": "2. Mahnung senden",
                "incoming": ["flow_unpaid_2"],
                "outgoing": ["flow_to_timer_3"],
                "implementation": "celery:dunning.send_second_dunning",
            },
            # Timer: 14 Tage warten
            {
                "id": "timer_14_days_3",
                "type": "intermediateCatchEvent",
                "name": "14 Tage warten",
                "incoming": ["flow_to_timer_3"],
                "outgoing": ["flow_timer_to_check_3"],
                "timer_type": "duration",
                "timer_value": "P14D",
            },
            # Gateway: Zahlung eingegangen?
            {
                "id": "gateway_payment_check_3",
                "type": "exclusiveGateway",
                "name": "Zahlung eingegangen?",
                "incoming": ["flow_timer_to_check_3"],
                "outgoing": ["flow_paid_3", "flow_unpaid_3"],
            },
            # Task 4: Dritte Mahnung (letzte Warnung)
            {
                "id": "task_third_dunning",
                "type": "serviceTask",
                "name": "3. Mahnung (letzte Warnung)",
                "incoming": ["flow_unpaid_3"],
                "outgoing": ["flow_to_decision"],
                "implementation": "celery:dunning.send_final_warning",
            },
            # Gateway: Inkasso oder Abschreibung?
            {
                "id": "gateway_final_decision",
                "type": "exclusiveGateway",
                "name": "Inkasso oder Abschreibung?",
                "incoming": ["flow_to_decision"],
                "outgoing": ["flow_to_inkasso", "flow_to_writeoff"],
            },
            # Task: Inkasso-Übergabe
            {
                "id": "task_inkasso",
                "type": "userTask",
                "name": "Inkasso-Übergabe vorbereiten",
                "incoming": ["flow_to_inkasso"],
                "outgoing": ["flow_to_end_inkasso"],
                "assignee_group": "Geschäftsführung",
                "form_key": "form:inkasso-handover",
            },
            # Task: Abschreibung
            {
                "id": "task_writeoff",
                "type": "serviceTask",
                "name": "Forderung abschreiben",
                "incoming": ["flow_to_writeoff"],
                "outgoing": ["flow_to_end_writeoff"],
                "implementation": "python:app.services.bpmn.dunning_tasks.write_off_invoice",
            },
            # End Events
            {
                "id": "end_paid",
                "type": "endEvent",
                "name": "Zahlung erhalten",
                "incoming": ["flow_paid_1", "flow_paid_2", "flow_paid_3"],
            },
            {
                "id": "end_inkasso",
                "type": "endEvent",
                "name": "An Inkasso übergeben",
                "incoming": ["flow_to_end_inkasso"],
            },
            {
                "id": "end_writeoff",
                "type": "endEvent",
                "name": "Abgeschrieben",
                "incoming": ["flow_to_end_writeoff"],
            },
            # Sequence Flows (gekürzt für Lesbarkeit)
            {"id": "flow_to_reminder", "type": "sequenceFlow", "source_ref": "start_dunning", "target_ref": "task_send_reminder"},
            {"id": "flow_reminder_to_timer", "type": "sequenceFlow", "source_ref": "task_send_reminder", "target_ref": "timer_14_days_1"},
            {"id": "flow_timer_to_check_1", "type": "sequenceFlow", "source_ref": "timer_14_days_1", "target_ref": "gateway_payment_check_1"},
            {"id": "flow_paid_1", "type": "sequenceFlow", "source_ref": "gateway_payment_check_1", "target_ref": "end_paid", "condition": "${paid == true}", "name": "Bezahlt"},
            {"id": "flow_unpaid_1", "type": "sequenceFlow", "source_ref": "gateway_payment_check_1", "target_ref": "task_first_dunning", "condition": "${paid == false}", "name": "Nicht bezahlt"},
            {"id": "flow_to_timer_2", "type": "sequenceFlow", "source_ref": "task_first_dunning", "target_ref": "timer_14_days_2"},
            {"id": "flow_timer_to_check_2", "type": "sequenceFlow", "source_ref": "timer_14_days_2", "target_ref": "gateway_payment_check_2"},
            {"id": "flow_paid_2", "type": "sequenceFlow", "source_ref": "gateway_payment_check_2", "target_ref": "end_paid", "condition": "${paid == true}", "name": "Bezahlt"},
            {"id": "flow_unpaid_2", "type": "sequenceFlow", "source_ref": "gateway_payment_check_2", "target_ref": "task_second_dunning", "condition": "${paid == false}", "name": "Nicht bezahlt"},
            {"id": "flow_to_timer_3", "type": "sequenceFlow", "source_ref": "task_second_dunning", "target_ref": "timer_14_days_3"},
            {"id": "flow_timer_to_check_3", "type": "sequenceFlow", "source_ref": "timer_14_days_3", "target_ref": "gateway_payment_check_3"},
            {"id": "flow_paid_3", "type": "sequenceFlow", "source_ref": "gateway_payment_check_3", "target_ref": "end_paid", "condition": "${paid == true}", "name": "Bezahlt"},
            {"id": "flow_unpaid_3", "type": "sequenceFlow", "source_ref": "gateway_payment_check_3", "target_ref": "task_third_dunning", "condition": "${paid == false}", "name": "Nicht bezahlt"},
            {"id": "flow_to_decision", "type": "sequenceFlow", "source_ref": "task_third_dunning", "target_ref": "gateway_final_decision"},
            {"id": "flow_to_inkasso", "type": "sequenceFlow", "source_ref": "gateway_final_decision", "target_ref": "task_inkasso", "condition": "${amount >= 500}", "name": "Inkasso"},
            {"id": "flow_to_writeoff", "type": "sequenceFlow", "source_ref": "gateway_final_decision", "target_ref": "task_writeoff", "condition": "${amount < 500}", "name": "Abschreiben"},
            {"id": "flow_to_end_inkasso", "type": "sequenceFlow", "source_ref": "task_inkasso", "target_ref": "end_inkasso"},
            {"id": "flow_to_end_writeoff", "type": "sequenceFlow", "source_ref": "task_writeoff", "target_ref": "end_writeoff"},
        ],
    },
    "variables_schema": {
        "invoice_id": {"type": "string", "required": True},
        "customer_id": {"type": "string", "required": True},
        "amount": {"type": "number", "required": True},
        "due_date": {"type": "date", "required": True},
        "paid": {"type": "boolean", "default": False},
        "dunning_level": {"type": "integer", "default": 0},
    },
}


# =============================================================================
# WORKFLOW TEMPLATE: Kunden-Onboarding
# =============================================================================

CUSTOMER_ONBOARDING_WORKFLOW: Dict[str, Any] = {
    "key": "customer-onboarding",
    "name": "Kunden-Onboarding",
    "description": """
Strukturierter Prozess zur Aufnahme neuer Kunden.

Ablauf:
1. Stammdaten erfassen (Kontaktdaten, Anschrift)
2. Bonitaetsprüfung (automatisch via Creditreform/SCHUFA)
3. Kreditlimit festlegen
4. Zahlungsbedingungen vereinbaren
5. Willkommenspaket versenden
6. Erstkontakt durch Vertrieb

Features:
- Parallele Aufgaben (Bonitaet + Stammdaten)
- Automatische Bonitaetsprüfung
- Integration mit CRM
""",
    "category": WorkflowCategory.KUNDEN,
    "tags": ["kunde", "onboarding", "neuanlage", "crm"],
    "process_data": {
        "id": "customer-onboarding",
        "name": "Kunden-Onboarding",
        "is_executable": True,
        "elements": [
            # Start
            {
                "id": "start_onboarding",
                "type": "startEvent",
                "name": "Neukunde angelegt",
                "outgoing": ["flow_to_parallel"],
            },
            # Parallel Gateway (Split)
            {
                "id": "gateway_parallel_start",
                "type": "parallelGateway",
                "name": "Parallele Prüfungen",
                "incoming": ["flow_to_parallel"],
                "outgoing": ["flow_to_stammdaten", "flow_to_bonitaet"],
            },
            # Branch 1: Stammdaten vervollständigen
            {
                "id": "task_stammdaten",
                "type": "userTask",
                "name": "Stammdaten vervollständigen",
                "incoming": ["flow_to_stammdaten"],
                "outgoing": ["flow_stammdaten_done"],
                "assignee_group": "Vertriebsinnendienst",
                "form_key": "form:customer-masterdata",
            },
            # Branch 2: Bonitaetsprüfung
            {
                "id": "task_bonitaet",
                "type": "serviceTask",
                "name": "Bonitaetsprüfung",
                "incoming": ["flow_to_bonitaet"],
                "outgoing": ["flow_bonitaet_done"],
                "implementation": "celery:customer.check_creditworthiness",
            },
            # Parallel Gateway (Join)
            {
                "id": "gateway_parallel_end",
                "type": "parallelGateway",
                "name": "Prüfungen abgeschlossen",
                "incoming": ["flow_stammdaten_done", "flow_bonitaet_done"],
                "outgoing": ["flow_to_bonitaet_check"],
            },
            # Gateway: Bonitaet OK?
            {
                "id": "gateway_bonitaet_ok",
                "type": "exclusiveGateway",
                "name": "Bonitaet OK?",
                "incoming": ["flow_to_bonitaet_check"],
                "outgoing": ["flow_bonitaet_ok", "flow_bonitaet_review"],
            },
            # Task: Kreditlimit festlegen
            {
                "id": "task_kreditlimit",
                "type": "userTask",
                "name": "Kreditlimit festlegen",
                "incoming": ["flow_bonitaet_ok"],
                "outgoing": ["flow_to_welcome"],
                "assignee_group": "Buchhaltung",
                "form_key": "form:credit-limit",
            },
            # Task: Manuelle Prüfung bei schlechter Bonitaet
            {
                "id": "task_manual_review",
                "type": "userTask",
                "name": "Manuelle Bonitaetsprüfung",
                "incoming": ["flow_bonitaet_review"],
                "outgoing": ["flow_review_decision"],
                "assignee_group": "Geschäftsführung",
                "form_key": "form:manual-credit-review",
            },
            # Gateway: Kunde annehmen?
            {
                "id": "gateway_accept",
                "type": "exclusiveGateway",
                "name": "Kunde annehmen?",
                "incoming": ["flow_review_decision"],
                "outgoing": ["flow_accept", "flow_reject"],
            },
            # Task: Willkommenspaket
            {
                "id": "task_welcome",
                "type": "serviceTask",
                "name": "Willkommenspaket versenden",
                "incoming": ["flow_to_welcome", "flow_accept"],
                "outgoing": ["flow_to_sales"],
                "implementation": "celery:customer.send_welcome_package",
            },
            # Task: Erstkontakt Vertrieb
            {
                "id": "task_sales_contact",
                "type": "userTask",
                "name": "Erstkontakt durch Vertrieb",
                "incoming": ["flow_to_sales"],
                "outgoing": ["flow_to_end_success"],
                "assignee_group": "Vertrieb",
                "form_key": "form:sales-first-contact",
                "due_date_duration": "P7D",
            },
            # Task: Ablehnung kommunizieren
            {
                "id": "task_reject",
                "type": "serviceTask",
                "name": "Ablehnung kommunizieren",
                "incoming": ["flow_reject"],
                "outgoing": ["flow_to_end_rejected"],
                "implementation": "celery:customer.send_rejection",
            },
            # End Events
            {
                "id": "end_success",
                "type": "endEvent",
                "name": "Onboarding abgeschlossen",
                "incoming": ["flow_to_end_success"],
            },
            {
                "id": "end_rejected",
                "type": "endEvent",
                "name": "Kunde abgelehnt",
                "incoming": ["flow_to_end_rejected"],
            },
            # Flows
            {"id": "flow_to_parallel", "type": "sequenceFlow", "source_ref": "start_onboarding", "target_ref": "gateway_parallel_start"},
            {"id": "flow_to_stammdaten", "type": "sequenceFlow", "source_ref": "gateway_parallel_start", "target_ref": "task_stammdaten"},
            {"id": "flow_to_bonitaet", "type": "sequenceFlow", "source_ref": "gateway_parallel_start", "target_ref": "task_bonitaet"},
            {"id": "flow_stammdaten_done", "type": "sequenceFlow", "source_ref": "task_stammdaten", "target_ref": "gateway_parallel_end"},
            {"id": "flow_bonitaet_done", "type": "sequenceFlow", "source_ref": "task_bonitaet", "target_ref": "gateway_parallel_end"},
            {"id": "flow_to_bonitaet_check", "type": "sequenceFlow", "source_ref": "gateway_parallel_end", "target_ref": "gateway_bonitaet_ok"},
            {"id": "flow_bonitaet_ok", "type": "sequenceFlow", "source_ref": "gateway_bonitaet_ok", "target_ref": "task_kreditlimit", "condition": "${credit_score >= 70}", "name": "Score >= 70"},
            {"id": "flow_bonitaet_review", "type": "sequenceFlow", "source_ref": "gateway_bonitaet_ok", "target_ref": "task_manual_review", "condition": "${credit_score < 70}", "name": "Score < 70"},
            {"id": "flow_to_welcome", "type": "sequenceFlow", "source_ref": "task_kreditlimit", "target_ref": "task_welcome"},
            {"id": "flow_review_decision", "type": "sequenceFlow", "source_ref": "task_manual_review", "target_ref": "gateway_accept"},
            {"id": "flow_accept", "type": "sequenceFlow", "source_ref": "gateway_accept", "target_ref": "task_welcome", "condition": "${accepted == true}", "name": "Angenommen"},
            {"id": "flow_reject", "type": "sequenceFlow", "source_ref": "gateway_accept", "target_ref": "task_reject", "condition": "${accepted == false}", "name": "Abgelehnt"},
            {"id": "flow_to_sales", "type": "sequenceFlow", "source_ref": "task_welcome", "target_ref": "task_sales_contact"},
            {"id": "flow_to_end_success", "type": "sequenceFlow", "source_ref": "task_sales_contact", "target_ref": "end_success"},
            {"id": "flow_to_end_rejected", "type": "sequenceFlow", "source_ref": "task_reject", "target_ref": "end_rejected"},
        ],
    },
    "variables_schema": {
        "customer_id": {"type": "string", "required": True},
        "company_name": {"type": "string", "required": True},
        "credit_score": {"type": "integer", "description": "Bonitaetsscore 0-100"},
        "credit_limit": {"type": "number", "description": "Festgelegtes Kreditlimit"},
        "accepted": {"type": "boolean", "description": "Manuell angenommen?"},
    },
}


# =============================================================================
# WORKFLOW TEMPLATE: Dokumenten-Klassifizierung
# =============================================================================

DOCUMENT_CLASSIFICATION_WORKFLOW: Dict[str, Any] = {
    "key": "document-classification",
    "name": "Dokumenten-Klassifizierung",
    "description": """
Automatische Klassifizierung und Routing von Dokumenten nach OCR.

Ablauf:
1. Dokument wird hochgeladen (Start-Event)
2. OCR-Verarbeitung (Service Task)
3. KI-Klassifizierung (Service Task)
4. Bei niedriger Confidence: Manuelle Prüfung
5. Routing basierend auf Dokumenttyp

Features:
- Automatische OCR-Auswahl (DeepSeek/GOT-OCR)
- Confidence-basiertes Routing
- Entity-Linking
""",
    "category": WorkflowCategory.DOKUMENTE,
    "tags": ["dokument", "ocr", "klassifizierung", "routing"],
    "process_data": {
        "id": "document-classification",
        "name": "Dokumenten-Klassifizierung",
        "is_executable": True,
        "elements": [
            {"id": "start_upload", "type": "startEvent", "name": "Dokument hochgeladen", "outgoing": ["flow_to_ocr"]},
            {
                "id": "task_ocr",
                "type": "serviceTask",
                "name": "OCR durchführen",
                "incoming": ["flow_to_ocr"],
                "outgoing": ["flow_to_classify"],
                "implementation": "celery:ocr.process_document",
            },
            {
                "id": "task_classify",
                "type": "serviceTask",
                "name": "KI-Klassifizierung",
                "incoming": ["flow_to_classify"],
                "outgoing": ["flow_to_confidence_check"],
                "implementation": "celery:ai.classify_document",
            },
            {
                "id": "gateway_confidence",
                "type": "exclusiveGateway",
                "name": "Confidence prüfen",
                "incoming": ["flow_to_confidence_check"],
                "outgoing": ["flow_high_confidence", "flow_low_confidence"],
            },
            {
                "id": "task_manual_review",
                "type": "userTask",
                "name": "Manuelle Klassifizierung",
                "incoming": ["flow_low_confidence"],
                "outgoing": ["flow_manual_done"],
                "assignee_group": "Dokumentenmanagement",
                "form_key": "form:document-classification",
            },
            {
                "id": "task_entity_linking",
                "type": "serviceTask",
                "name": "Entity-Verknüpfung",
                "incoming": ["flow_high_confidence", "flow_manual_done"],
                "outgoing": ["flow_to_routing"],
                "implementation": "celery:entity.link_document",
            },
            {
                "id": "gateway_doctype",
                "type": "exclusiveGateway",
                "name": "Nach Dokumenttyp routen",
                "incoming": ["flow_to_routing"],
                "outgoing": ["flow_invoice", "flow_order", "flow_other"],
            },
            {
                "id": "task_invoice_workflow",
                "type": "serviceTask",
                "name": "Rechnungs-Workflow starten",
                "incoming": ["flow_invoice"],
                "outgoing": ["flow_to_end_invoice"],
                "implementation": "celery:bpmn.start_invoice_approval",
            },
            {
                "id": "task_order_workflow",
                "type": "serviceTask",
                "name": "Bestell-Workflow starten",
                "incoming": ["flow_order"],
                "outgoing": ["flow_to_end_order"],
                "implementation": "celery:bpmn.start_order_processing",
            },
            {
                "id": "task_archive",
                "type": "serviceTask",
                "name": "Dokument archivieren",
                "incoming": ["flow_other"],
                "outgoing": ["flow_to_end_archive"],
                "implementation": "celery:document.archive",
            },
            {"id": "end_invoice", "type": "endEvent", "name": "An Rechnungs-WF", "incoming": ["flow_to_end_invoice"]},
            {"id": "end_order", "type": "endEvent", "name": "An Bestell-WF", "incoming": ["flow_to_end_order"]},
            {"id": "end_archive", "type": "endEvent", "name": "Archiviert", "incoming": ["flow_to_end_archive"]},
            # Flows
            {"id": "flow_to_ocr", "type": "sequenceFlow", "source_ref": "start_upload", "target_ref": "task_ocr"},
            {"id": "flow_to_classify", "type": "sequenceFlow", "source_ref": "task_ocr", "target_ref": "task_classify"},
            {"id": "flow_to_confidence_check", "type": "sequenceFlow", "source_ref": "task_classify", "target_ref": "gateway_confidence"},
            {"id": "flow_high_confidence", "type": "sequenceFlow", "source_ref": "gateway_confidence", "target_ref": "task_entity_linking", "condition": "${classification_confidence >= 0.85}", "name": ">= 85%"},
            {"id": "flow_low_confidence", "type": "sequenceFlow", "source_ref": "gateway_confidence", "target_ref": "task_manual_review", "condition": "${classification_confidence < 0.85}", "name": "< 85%"},
            {"id": "flow_manual_done", "type": "sequenceFlow", "source_ref": "task_manual_review", "target_ref": "task_entity_linking"},
            {"id": "flow_to_routing", "type": "sequenceFlow", "source_ref": "task_entity_linking", "target_ref": "gateway_doctype"},
            {"id": "flow_invoice", "type": "sequenceFlow", "source_ref": "gateway_doctype", "target_ref": "task_invoice_workflow", "condition": "${document_type == 'invoice'}", "name": "Rechnung"},
            {"id": "flow_order", "type": "sequenceFlow", "source_ref": "gateway_doctype", "target_ref": "task_order_workflow", "condition": "${document_type == 'order'}", "name": "Bestellung"},
            {"id": "flow_other", "type": "sequenceFlow", "source_ref": "gateway_doctype", "target_ref": "task_archive", "name": "Sonstige"},
            {"id": "flow_to_end_invoice", "type": "sequenceFlow", "source_ref": "task_invoice_workflow", "target_ref": "end_invoice"},
            {"id": "flow_to_end_order", "type": "sequenceFlow", "source_ref": "task_order_workflow", "target_ref": "end_order"},
            {"id": "flow_to_end_archive", "type": "sequenceFlow", "source_ref": "task_archive", "target_ref": "end_archive"},
        ],
    },
    "variables_schema": {
        "document_id": {"type": "string", "required": True},
        "document_type": {"type": "string", "description": "Erkannter Dokumenttyp"},
        "classification_confidence": {"type": "number", "description": "KI-Confidence 0-1"},
        "entity_id": {"type": "string", "description": "Verknüpfte Entity"},
    },
}


# =============================================================================
# ALL TEMPLATES
# =============================================================================

ALL_WORKFLOW_TEMPLATES: List[Dict[str, Any]] = [
    INVOICE_APPROVAL_WORKFLOW,
    DUNNING_PROCESS_WORKFLOW,
    CUSTOMER_ONBOARDING_WORKFLOW,
    DOCUMENT_CLASSIFICATION_WORKFLOW,
]


def get_workflow_template(key: str) -> Dict[str, Any] | None:
    """Gibt ein Workflow-Template nach Key zurück."""
    for template in ALL_WORKFLOW_TEMPLATES:
        if template["key"] == key:
            return template
    return None


def list_workflow_templates(category: WorkflowCategory | None = None) -> List[Dict[str, Any]]:
    """Listet alle verfügbaren Workflow-Templates auf.

    Args:
        category: Optional Filter nach Kategorie

    Returns:
        Liste der Templates (ohne process_data für Übersicht)
    """
    templates = ALL_WORKFLOW_TEMPLATES

    if category:
        templates = [t for t in templates if t.get("category") == category]

    # Nur Metadaten zurückgeben
    return [
        {
            "key": t["key"],
            "name": t["name"],
            "description": t["description"],
            "category": t.get("category"),
            "tags": t.get("tags", []),
        }
        for t in templates
    ]
