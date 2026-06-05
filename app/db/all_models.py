# -*- coding: utf-8 -*-
"""Zentraler Modell-Aggregator (G4 DB-Hygiene).

Dieses Modul importiert ALLE ``app.db.models_*``-Module (sowie das Kernmodul
``app.db.models``), damit jedes ORM-Modell genau einmal registriert und in
``Base.metadata`` sichtbar wird. Hintergrund: Einige Modellmodule wurden
nirgends importiert ("verwaiste" Module) und waren dadurch fuer
``Base.metadata`` unsichtbar — z. B. fuer Vollstaendigkeits-Pruefungen,
Tooling oder Autogenerate.

WICHTIG:
- Es werden bewusst NUR Module importiert (``import app.db.models_x``),
  KEINE Einzel-Symbole re-exportiert (``from ... import Name``). Das vermeidet
  Zirkular-Importe zwischen den Modellmodulen.
- Die Reihenfolge ist alphabetisch und ohne Bedeutung: SQLAlchemy registriert
  Tabellen/Klassen anhand des Imports, nicht anhand der Reihenfolge hier.

Verwaiste Module — Entscheidung:
- ``models_categorization_feedback`` (Tabelle ``categorization_feedback``) und
  ``models_knowledge_graph`` (Tabellen ``knowledge_graph_relations``,
  ``entity_resolutions``, ``knowledge_graph_snapshots``) definieren ECHTE,
  migrierte Tabellen. Sie waren lediglich nirgends importiert. Korrekt ist
  daher die AUFNAHME hier (statt Entfernen) — so werden ihre Tabellen wieder
  fuer ``Base.metadata`` sichtbar, ohne DB-Schema zu veraendern.

Cross-Stream-Abhaengigkeit (ausserhalb G4-Scope):
- ``alembic/env.py`` sollte ``import app.db.all_models`` nutzen, damit
  Autogenerate alle Tabellen sieht. Diese Umstellung gehoert NICHT zu G4
  (Scope: nur ``app/services``, ``app/workers``, ``app/db``) und ist hier nur
  als Hinweis vermerkt.
"""

# Kernmodul zuerst: definiert Base sowie die zentralen Modelle.
import app.db.models  # noqa: F401

# Alle Satelliten-Modellmodule (alphabetisch).
import app.db.models_active_learning  # noqa: F401
import app.db.models_adhoc_report  # noqa: F401
import app.db.models_adhoc_reporting  # noqa: F401
import app.db.models_ai_conversation  # noqa: F401
import app.db.models_ai_ml  # noqa: F401
import app.db.models_alert  # noqa: F401
import app.db.models_annotations  # noqa: F401
import app.db.models_annotations_extended  # noqa: F401
import app.db.models_anomaly  # noqa: F401
import app.db.models_approval_extended  # noqa: F401
import app.db.models_approval_matrix  # noqa: F401
import app.db.models_auth_access  # noqa: F401
import app.db.models_autonomy  # noqa: F401
import app.db.models_banking  # noqa: F401
import app.db.models_banking_connection  # noqa: F401
import app.db.models_barcode  # noqa: F401
import app.db.models_base  # noqa: F401
import app.db.models_budget  # noqa: F401
import app.db.models_cash_company  # noqa: F401
import app.db.models_categorization_feedback  # noqa: F401
import app.db.models_cdc  # noqa: F401
import app.db.models_chat_actions  # noqa: F401
import app.db.models_clustering  # noqa: F401
import app.db.models_collaboration  # noqa: F401
import app.db.models_comments  # noqa: F401
import app.db.models_communication  # noqa: F401
import app.db.models_compliance  # noqa: F401
import app.db.models_consent  # noqa: F401
import app.db.models_contract  # noqa: F401
import app.db.models_custom_fields  # noqa: F401
import app.db.models_dashboard  # noqa: F401
import app.db.models_dashboard_share  # noqa: F401
import app.db.models_data_quality  # noqa: F401
import app.db.models_datev  # noqa: F401
import app.db.models_delegation  # noqa: F401
import app.db.models_document_lifecycle  # noqa: F401
import app.db.models_dropship_tax  # noqa: F401
import app.db.models_einvoice  # noqa: F401
import app.db.models_encryption  # noqa: F401
import app.db.models_entity_business  # noqa: F401
import app.db.models_erp_import  # noqa: F401
import app.db.models_esg  # noqa: F401
import app.db.models_folder  # noqa: F401
import app.db.models_fraud  # noqa: F401
import app.db.models_fx  # noqa: F401
import app.db.models_gdpr_compliance  # noqa: F401
import app.db.models_german_finance  # noqa: F401
import app.db.models_gl_posting  # noqa: F401
import app.db.models_hr  # noqa: F401
import app.db.models_insights  # noqa: F401
import app.db.models_integration  # noqa: F401
import app.db.models_integration_sync  # noqa: F401
import app.db.models_integrity  # noqa: F401
import app.db.models_inventory  # noqa: F401
import app.db.models_invoice  # noqa: F401
import app.db.models_ki_pipeline  # noqa: F401
import app.db.models_knowledge_graph  # noqa: F401
import app.db.models_learning_autonomy  # noqa: F401
import app.db.models_lineage  # noqa: F401
import app.db.models_misc  # noqa: F401
import app.db.models_notification  # noqa: F401
import app.db.models_notification_template  # noqa: F401
import app.db.models_ocr_feedback  # noqa: F401
import app.db.models_ocr_template  # noqa: F401
import app.db.models_ocr_validation  # noqa: F401
import app.db.models_partitioning  # noqa: F401
import app.db.models_po_matching  # noqa: F401
import app.db.models_portal  # noqa: F401
import app.db.models_prediction_feedback  # noqa: F401
import app.db.models_predictions  # noqa: F401
import app.db.models_privat_contracts  # noqa: F401
import app.db.models_privat_enterprise  # noqa: F401
import app.db.models_privat_space  # noqa: F401
import app.db.models_proactive_assistant  # noqa: F401
import app.db.models_process_mining  # noqa: F401
import app.db.models_project  # noqa: F401
import app.db.models_rag  # noqa: F401
import app.db.models_recurring_invoice  # noqa: F401
import app.db.models_report  # noqa: F401
import app.db.models_rules  # noqa: F401
import app.db.models_saved_search  # noqa: F401
import app.db.models_signature  # noqa: F401
import app.db.models_smart_dashboard  # noqa: F401
import app.db.models_surya_training  # noqa: F401
import app.db.models_team  # noqa: F401
import app.db.models_template_knowledge  # noqa: F401
import app.db.models_tenant_config  # noqa: F401
import app.db.models_versioning  # noqa: F401
import app.db.models_webhook_inbound  # noqa: F401
import app.db.models_webhooks  # noqa: F401
import app.db.models_workflow  # noqa: F401
import app.db.models_workflow_stage  # noqa: F401
import app.db.models_workflow_versioning  # noqa: F401
import app.db.models_year_end  # noqa: F401
# Subpackages mit Mapped-Klassen (keine models_*-Module -> sonst von configure_mappers vermisst)
import app.db.bpmn_models.bpmn  # noqa: F401 - ProcessDefinition/ProcessInstance
import app.db.bpmn_models.gobd  # noqa: F401
