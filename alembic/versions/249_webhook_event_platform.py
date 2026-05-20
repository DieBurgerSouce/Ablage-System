# -*- coding: utf-8 -*-
"""Webhook Event Platform: Outbound Webhooks mit Event-Bus, Replay und DLQ.

Revision ID: 249
Revises: 248
Create Date: 2026-02-21

Erstellt drei Tabellen:
- webhook_endpoints: Registrierte Empfaenger-URLs mit HMAC-Konfiguration
- webhook_deliveries: Zustellungsprotokoll mit Retry-Tracking und DLQ
- webhook_event_log: Unveraenderbares Event-Journal fuer Replay-Funktionalitaet
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "249"
down_revision = "248"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Erstellt Webhook-Event-Platform-Tabellen."""

    # ==========================================================================
    # Tabelle: webhook_endpoints
    # Registrierte Outbound-Webhook-Empfaenger pro Mandant
    # ==========================================================================
    op.create_table(
        "webhook_endpoints",

        # Primaerschluessel
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            comment="Eindeutiger Endpoint-Bezeichner",
        ),

        # Multi-Tenancy
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
            comment="Mandant (Multi-Tenancy)",
        ),

        # Zielkonfiguration
        sa.Column(
            "url",
            sa.String(2000),
            nullable=False,
            comment="Ziel-URL fuer Webhook-Zustellungen",
        ),
        sa.Column(
            "description",
            sa.Text,
            nullable=True,
            comment="Optionale Beschreibung des Endpoints",
        ),

        # Sicherheit - Secret als Hash, nie im Klartext
        sa.Column(
            "secret_hash",
            sa.String(256),
            nullable=False,
            comment="HMAC-SHA256 Hash des Webhook-Secrets (nie Klartext)",
        ),

        # Event-Filter
        sa.Column(
            "event_types",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
            comment="Abonnierte Event-Typen (leer = alle Events)",
        ),

        # Status
        sa.Column(
            "is_active",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
            comment="Aktiv/Inaktiv-Schalter",
        ),

        # Benutzerdefinierte Header
        sa.Column(
            "headers",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Optionale HTTP-Header fuer Zustellungen",
        ),

        # Retry-Konfiguration
        sa.Column(
            "retry_policy",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text(
                '\'{"max_retries": 3, "backoff_factor": 2, "timeout_seconds": 30}\'::jsonb'
            ),
            comment="Retry-Richtlinie: max_retries, backoff_factor, timeout_seconds",
        ),

        # Zeitstempel
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),

        comment="Registrierte Outbound-Webhook-Endpoints pro Mandant",
    )

    # Indexe fuer webhook_endpoints
    op.create_index(
        "ix_webhook_endpoints_company_id",
        "webhook_endpoints",
        ["company_id"],
    )
    op.create_index(
        "ix_webhook_endpoints_company_active",
        "webhook_endpoints",
        ["company_id", "is_active"],
    )

    # ==========================================================================
    # Tabelle: webhook_deliveries
    # Zustellungsprotokoll mit Retry-Tracking und DLQ-Unterstuetzung
    # ==========================================================================
    op.create_table(
        "webhook_deliveries",

        # Primaerschluessel
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            comment="Eindeutiger Zustellungs-Bezeichner",
        ),

        # Fremdschluessel
        sa.Column(
            "endpoint_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("webhook_endpoints.id", ondelete="CASCADE"),
            nullable=False,
            comment="Zugehoerige Endpoint-Konfiguration",
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
            comment="Mandant fuer Multi-Tenancy-Isolation",
        ),

        # Event-Referenz
        sa.Column(
            "event_type",
            sa.String(100),
            nullable=False,
            comment="Event-Typ, z.B. document.created",
        ),
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Referenz auf den Quell-Event (WebhookEventLog.id)",
        ),

        # Payload
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="Vollstaendiges Event-Payload",
        ),

        # Status
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'pending'"),
            comment="Zustellstatus: pending, delivered, failed, dlq",
        ),

        # Versuchszaehler
        sa.Column(
            "attempts",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
            comment="Anzahl durchgefuehrter Zustellversuche",
        ),
        sa.Column(
            "max_attempts",
            sa.Integer,
            nullable=False,
            server_default=sa.text("3"),
            comment="Maximale Anzahl Versuche bevor DLQ",
        ),

        # HTTP-Antwort
        sa.Column(
            "response_status_code",
            sa.Integer,
            nullable=True,
            comment="HTTP-Statuscode der letzten Antwort",
        ),
        sa.Column(
            "response_body",
            sa.Text,
            nullable=True,
            comment="Gekuerzte HTTP-Antwort (max 1000 Zeichen)",
        ),

        # Timing
        sa.Column(
            "last_attempt_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Zeitstempel des letzten Zustellversuchs",
        ),
        sa.Column(
            "next_retry_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Geplanter Zeitpunkt fuer den naechsten Retry",
        ),
        sa.Column(
            "delivered_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Zeitstempel der erfolgreichen Zustellung",
        ),

        # Erstellungszeitpunkt
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),

        comment="Zustellungsprotokoll fuer Outbound-Webhook-Events mit DLQ",
    )

    # Indexe fuer webhook_deliveries
    op.create_index(
        "ix_webhook_deliveries_endpoint_id",
        "webhook_deliveries",
        ["endpoint_id"],
    )
    op.create_index(
        "ix_webhook_deliveries_company_id",
        "webhook_deliveries",
        ["company_id"],
    )
    op.create_index(
        "ix_webhook_deliveries_status",
        "webhook_deliveries",
        ["status"],
    )
    op.create_index(
        "ix_webhook_deliveries_event_id",
        "webhook_deliveries",
        ["event_id"],
    )
    op.create_index(
        "ix_webhook_deliveries_endpoint_status",
        "webhook_deliveries",
        ["endpoint_id", "status"],
    )
    op.create_index(
        "ix_webhook_deliveries_company_event",
        "webhook_deliveries",
        ["company_id", "event_type"],
    )
    # Partial index fuer ausstehende Retries (effizienter Worker-Scan)
    op.create_index(
        "ix_webhook_deliveries_retry_pending",
        "webhook_deliveries",
        ["status", "next_retry_at"],
        postgresql_where=sa.text("status IN ('pending', 'failed') AND next_retry_at IS NOT NULL"),
    )

    # ==========================================================================
    # Tabelle: webhook_event_log
    # Unveraenderbares Event-Journal fuer Replay-Funktionalitaet
    # ==========================================================================
    op.create_table(
        "webhook_event_log",

        # Primaerschluessel
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            comment="Eindeutiger Event-Bezeichner",
        ),

        # Multi-Tenancy
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
            comment="Mandant fuer Multi-Tenancy-Isolation",
        ),

        # Event-Klassifikation
        sa.Column(
            "event_type",
            sa.String(100),
            nullable=False,
            comment="Event-Typ, z.B. document.created, invoice.updated",
        ),

        # Quell-Referenz
        sa.Column(
            "source_table",
            sa.String(100),
            nullable=False,
            comment="Quell-Tabelle des Events, z.B. documents, invoices",
        ),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Primaerschluessel des ausloesenden Datensatzes",
        ),

        # Event-Payload fuer Replay
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="Vollstaendiges Event-Payload fuer Replay-Zustellungen",
        ),

        # Zeitstempel (append-only)
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),

        comment="Unveraenderbares Event-Journal fuer Webhook-Replay",
    )

    # Indexe fuer webhook_event_log
    op.create_index(
        "ix_webhook_event_log_company_id",
        "webhook_event_log",
        ["company_id"],
    )
    op.create_index(
        "ix_webhook_event_log_created_at",
        "webhook_event_log",
        ["created_at"],
    )
    op.create_index(
        "ix_webhook_event_log_company_type",
        "webhook_event_log",
        ["company_id", "event_type", "created_at"],
    )
    op.create_index(
        "ix_webhook_event_log_source",
        "webhook_event_log",
        ["company_id", "source_table", "source_id"],
    )


def downgrade() -> None:
    """Entfernt Webhook-Event-Platform-Tabellen."""

    # Indexe und Tabellen in umgekehrter Reihenfolge entfernen

    # webhook_event_log
    op.drop_index("ix_webhook_event_log_source", table_name="webhook_event_log")
    op.drop_index("ix_webhook_event_log_company_type", table_name="webhook_event_log")
    op.drop_index("ix_webhook_event_log_created_at", table_name="webhook_event_log")
    op.drop_index("ix_webhook_event_log_company_id", table_name="webhook_event_log")
    op.drop_table("webhook_event_log")

    # webhook_deliveries
    op.drop_index("ix_webhook_deliveries_retry_pending", table_name="webhook_deliveries")
    op.drop_index("ix_webhook_deliveries_company_event", table_name="webhook_deliveries")
    op.drop_index("ix_webhook_deliveries_endpoint_status", table_name="webhook_deliveries")
    op.drop_index("ix_webhook_deliveries_event_id", table_name="webhook_deliveries")
    op.drop_index("ix_webhook_deliveries_status", table_name="webhook_deliveries")
    op.drop_index("ix_webhook_deliveries_company_id", table_name="webhook_deliveries")
    op.drop_index("ix_webhook_deliveries_endpoint_id", table_name="webhook_deliveries")
    op.drop_table("webhook_deliveries")

    # webhook_endpoints
    op.drop_index("ix_webhook_endpoints_company_active", table_name="webhook_endpoints")
    op.drop_index("ix_webhook_endpoints_company_id", table_name="webhook_endpoints")
    op.drop_table("webhook_endpoints")
