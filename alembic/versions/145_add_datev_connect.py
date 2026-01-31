# -*- coding: utf-8 -*-
"""
DATEV Connect Integration - Vollstaendige DATEVconnect API Integration.

Revision ID: 145_add_datev_connect
Revises: 144_add_insights_and_autonomy
Create Date: 2026-01-30

Features:
- DATEV Verbindungskonfiguration mit OAuth2
- Kontenplan-Synchronisation (SKR03/SKR04)
- Buchungssaetze mit GoBD-Compliance
- Beleglinks fuer Belegbilder-Archivierung
- Kontierungs-Patterns fuer ML-basierte Vorschlaege
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Revision identifiers
revision = "145_add_datev_connect"
down_revision = "144_add_insights_and_autonomy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Erstellt DATEV Connect Tabellen."""

    # ==========================================================================
    # 1. DATEV Connections - OAuth2-basierte Verbindungskonfiguration
    # ==========================================================================
    op.create_table(
        "datev_connections",
        # Primary Key
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),

        # Foreign Keys
        sa.Column(
            "erp_connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("erp_connections.id", ondelete="SET NULL"),
            nullable=True,
            comment="Optionale Verknuepfung mit ERP-Connection"
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
            comment="Multi-Tenant Zuordnung"
        ),

        # DATEV Identifikation
        sa.Column(
            "name",
            sa.String(100),
            nullable=False,
            comment="Anzeigename der Verbindung"
        ),
        sa.Column(
            "beraternummer",
            sa.String(10),
            nullable=False,
            comment="DATEV Beraternummer (5-stellig)"
        ),
        sa.Column(
            "mandantennummer",
            sa.String(10),
            nullable=False,
            comment="DATEV Mandantennummer (5-stellig)"
        ),
        sa.Column(
            "wirtschaftsjahr_beginn",
            sa.Integer(),
            nullable=False,
            default=1,
            comment="Monat des Wirtschaftsjahresbeginns (1-12)"
        ),

        # DATEVconnect OAuth2 Credentials
        sa.Column(
            "client_id",
            sa.String(100),
            nullable=True,
            comment="DATEVconnect OAuth2 Client ID"
        ),
        sa.Column(
            "client_secret_encrypted",
            sa.Text(),
            nullable=True,
            comment="AES-256-GCM verschluesseltes Client Secret"
        ),
        sa.Column(
            "redirect_uri",
            sa.String(500),
            nullable=True,
            comment="OAuth2 Redirect URI"
        ),
        sa.Column(
            "access_token_encrypted",
            sa.Text(),
            nullable=True,
            comment="AES-256-GCM verschluesselter Access Token"
        ),
        sa.Column(
            "refresh_token_encrypted",
            sa.Text(),
            nullable=True,
            comment="AES-256-GCM verschluesselter Refresh Token"
        ),
        sa.Column(
            "token_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Token Ablaufzeitpunkt"
        ),

        # API-Einstellungen
        sa.Column(
            "api_environment",
            sa.String(20),
            nullable=False,
            default="production",
            comment="API Umgebung: production, sandbox"
        ),
        sa.Column(
            "api_version",
            sa.String(10),
            nullable=False,
            default="v1",
            comment="API Version"
        ),
        sa.Column(
            "enabled_features",
            postgresql.JSONB,
            nullable=False,
            default=["stammdaten", "buchungen", "belege"],
            comment="Aktivierte Features als JSON Array"
        ),

        # Buchhaltungs-Einstellungen
        sa.Column(
            "kontenrahmen",
            sa.String(10),
            nullable=False,
            default="SKR03",
            comment="Kontenrahmen: SKR03, SKR04"
        ),
        sa.Column(
            "sachkontenlange",
            sa.Integer(),
            nullable=False,
            default=4,
            comment="Laenge der Sachkonten (4-8)"
        ),
        sa.Column(
            "personenkontenlange",
            sa.Integer(),
            nullable=False,
            default=5,
            comment="Laenge der Personenkonten (5-9)"
        ),
        sa.Column(
            "buchungsmodus",
            sa.String(20),
            nullable=False,
            default="manuell",
            comment="Buchungsmodus: automatisch, manuell, bestaetigung"
        ),

        # Standard-Konten
        sa.Column(
            "sammelkonto_debitoren",
            sa.String(10),
            nullable=True,
            comment="Sammelkonto Debitoren (z.B. 1400)"
        ),
        sa.Column(
            "sammelkonto_kreditoren",
            sa.String(10),
            nullable=True,
            comment="Sammelkonto Kreditoren (z.B. 1600)"
        ),
        sa.Column(
            "erloskonto_standard",
            sa.String(10),
            nullable=True,
            comment="Standard-Erloeskonto (z.B. 8400)"
        ),
        sa.Column(
            "aufwandskonto_standard",
            sa.String(10),
            nullable=True,
            comment="Standard-Aufwandskonto (z.B. 4400)"
        ),

        # GoBD-Compliance
        sa.Column(
            "gobd_enabled",
            sa.Boolean(),
            nullable=False,
            default=True,
            comment="GoBD-Compliance aktiviert"
        ),
        sa.Column(
            "festschreibung_automatisch",
            sa.Boolean(),
            nullable=False,
            default=False,
            comment="Automatische Festschreibung am Monatsende"
        ),
        sa.Column(
            "beleglink_prefix",
            sa.String(500),
            nullable=True,
            comment="URL-Prefix fuer Beleglinks"
        ),

        # Sync-Status
        sa.Column(
            "connection_status",
            sa.String(30),
            nullable=False,
            default="disconnected",
            comment="Verbindungsstatus"
        ),
        sa.Column(
            "last_error",
            sa.Text(),
            nullable=True,
            comment="Letzte Fehlermeldung"
        ),
        sa.Column(
            "last_connection_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Letzte erfolgreiche Verbindung"
        ),
        sa.Column(
            "last_stammdaten_sync",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Letzter Stammdaten-Sync"
        ),
        sa.Column(
            "last_buchungen_sync",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Letzter Buchungen-Sync"
        ),
        sa.Column(
            "last_belege_sync",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Letzter Belegbilder-Sync"
        ),

        # Status
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            default=True,
            comment="Verbindung aktiv"
        ),

        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True
        ),
        sa.Column(
            "updated_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True
        ),

        # Constraints
        sa.CheckConstraint(
            "kontenrahmen IN ('SKR03', 'SKR04')",
            name="ck_datev_conn_kontenrahmen"
        ),
        sa.CheckConstraint(
            "sachkontenlange BETWEEN 4 AND 8",
            name="ck_datev_conn_sachkontenlange"
        ),
        sa.CheckConstraint(
            "personenkontenlange BETWEEN 5 AND 9",
            name="ck_datev_conn_personenkontenlange"
        ),
        sa.CheckConstraint(
            "wirtschaftsjahr_beginn BETWEEN 1 AND 12",
            name="ck_datev_conn_wj_beginn"
        ),
        sa.CheckConstraint(
            "api_environment IN ('production', 'sandbox')",
            name="ck_datev_conn_api_env"
        ),
        sa.CheckConstraint(
            "buchungsmodus IN ('automatisch', 'manuell', 'bestaetigung')",
            name="ck_datev_conn_buchungsmodus"
        ),

        # Unique Constraint: Ein Mandant pro Company
        sa.UniqueConstraint(
            "company_id", "beraternummer", "mandantennummer",
            name="uq_datev_conn_mandant"
        ),
    )

    # Indexes fuer datev_connections
    op.create_index(
        "ix_datev_connections_company_id",
        "datev_connections",
        ["company_id"]
    )
    op.create_index(
        "ix_datev_connections_status",
        "datev_connections",
        ["connection_status"]
    )
    op.create_index(
        "ix_datev_connections_active",
        "datev_connections",
        ["is_active"]
    )

    # ==========================================================================
    # 2. DATEV Kontenplan - Synchronisierter Kontenrahmen
    # ==========================================================================
    op.create_table(
        "datev_kontenplan",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("datev_connections.id", ondelete="CASCADE"),
            nullable=False
        ),

        # Kontodaten
        sa.Column(
            "kontonummer",
            sa.String(10),
            nullable=False,
            comment="Kontonummer"
        ),
        sa.Column(
            "kontobezeichnung",
            sa.String(200),
            nullable=False,
            comment="Kontobezeichnung"
        ),
        sa.Column(
            "kontotyp",
            sa.String(30),
            nullable=False,
            comment="Kontotyp: sachkonto, personenkonto, anlage"
        ),
        sa.Column(
            "kontenklasse",
            sa.String(5),
            nullable=True,
            comment="Kontenklasse (0-9)"
        ),
        sa.Column(
            "steuercode_default",
            sa.String(5),
            nullable=True,
            comment="Standard-Steuerschluessel"
        ),
        sa.Column(
            "ist_automatikkonto",
            sa.Boolean(),
            nullable=False,
            default=False,
            comment="Automatikkonto (automatische Steuerberechnung)"
        ),
        sa.Column(
            "ist_gesperrt",
            sa.Boolean(),
            nullable=False,
            default=False,
            comment="Konto gesperrt"
        ),

        # Hierarchie
        sa.Column(
            "sammelkonto",
            sa.String(10),
            nullable=True,
            comment="Uebergeordnetes Sammelkonto"
        ),

        # DATEV-Referenz
        sa.Column(
            "datev_id",
            sa.String(50),
            nullable=True,
            comment="ID in DATEV"
        ),

        # Sync-Status
        sa.Column(
            "last_synced_at",
            sa.DateTime(timezone=True),
            nullable=True
        ),

        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False
        ),

        # Constraints
        sa.CheckConstraint(
            "kontotyp IN ('sachkonto', 'personenkonto', 'anlage', 'statistik')",
            name="ck_datev_konto_typ"
        ),

        # Unique: Kontonummer pro Connection
        sa.UniqueConstraint(
            "connection_id", "kontonummer",
            name="uq_datev_kontenplan_konto"
        ),
    )

    # Indexes fuer datev_kontenplan
    op.create_index(
        "ix_datev_kontenplan_connection",
        "datev_kontenplan",
        ["connection_id"]
    )
    op.create_index(
        "ix_datev_kontenplan_nummer",
        "datev_kontenplan",
        ["kontonummer"]
    )
    op.create_index(
        "ix_datev_kontenplan_typ",
        "datev_kontenplan",
        ["kontotyp"]
    )
    op.create_index(
        "ix_datev_kontenplan_klasse",
        "datev_kontenplan",
        ["kontenklasse"]
    )

    # ==========================================================================
    # 3. DATEV Buchungen - Buchungssaetze mit GoBD-Compliance
    # ==========================================================================
    op.create_table(
        "datev_buchungen",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("datev_connections.id", ondelete="CASCADE"),
            nullable=False
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
            nullable=True,
            comment="Verknuepftes Dokument"
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False
        ),

        # Buchungsdaten (DATEV-Format)
        sa.Column(
            "umsatz",
            sa.Numeric(15, 2),
            nullable=False,
            comment="Umsatz in EUR"
        ),
        sa.Column(
            "soll_haben",
            sa.String(1),
            nullable=False,
            comment="S=Soll, H=Haben"
        ),
        sa.Column(
            "konto",
            sa.String(10),
            nullable=False,
            comment="Konto (Soll bei S, Haben bei H)"
        ),
        sa.Column(
            "gegenkonto",
            sa.String(10),
            nullable=False,
            comment="Gegenkonto"
        ),
        sa.Column(
            "bu_schluessel",
            sa.String(5),
            nullable=True,
            comment="Steuerschluessel (BU-Schluessel)"
        ),
        sa.Column(
            "belegdatum",
            sa.Date(),
            nullable=False,
            comment="Belegdatum"
        ),
        sa.Column(
            "belegfeld_1",
            sa.String(36),
            nullable=True,
            comment="Belegfeld 1 (Rechnungsnummer)"
        ),
        sa.Column(
            "belegfeld_2",
            sa.String(12),
            nullable=True,
            comment="Belegfeld 2"
        ),
        sa.Column(
            "buchungstext",
            sa.String(60),
            nullable=True,
            comment="Buchungstext (max 60 Zeichen)"
        ),

        # Erweiterte DATEV-Felder
        sa.Column(
            "kostenstelle_1",
            sa.String(20),
            nullable=True,
            comment="Kostenstelle 1"
        ),
        sa.Column(
            "kostenstelle_2",
            sa.String(20),
            nullable=True,
            comment="Kostenstelle 2"
        ),
        sa.Column(
            "kostentraeger",
            sa.String(20),
            nullable=True,
            comment="Kostentraeger"
        ),
        sa.Column(
            "skonto",
            sa.Numeric(15, 2),
            nullable=True,
            comment="Skontobetrag"
        ),
        sa.Column(
            "leistungsdatum",
            sa.Date(),
            nullable=True,
            comment="Leistungsdatum"
        ),
        sa.Column(
            "zahlungsbedingung",
            sa.String(20),
            nullable=True,
            comment="Zahlungsbedingung"
        ),

        # Zusatz-Informationen
        sa.Column(
            "waehrung",
            sa.String(3),
            nullable=False,
            default="EUR",
            comment="Waehrung (ISO 4217)"
        ),
        sa.Column(
            "kurs",
            sa.Numeric(12, 6),
            nullable=True,
            comment="Wechselkurs bei Fremdwaehrung"
        ),
        sa.Column(
            "basis_umsatz",
            sa.Numeric(15, 2),
            nullable=True,
            comment="Basisumsatz bei Fremdwaehrung"
        ),

        # GoBD-Compliance
        sa.Column(
            "buchungs_guid",
            sa.String(36),
            nullable=False,
            comment="Eindeutige unveraenderliche Buchungs-ID (GoBD)"
        ),
        sa.Column(
            "ist_festgeschrieben",
            sa.Boolean(),
            nullable=False,
            default=False,
            comment="Buchung festgeschrieben (unveraenderlich)"
        ),
        sa.Column(
            "festschreibung_datum",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Zeitpunkt der Festschreibung"
        ),
        sa.Column(
            "festschreibung_hash",
            sa.String(64),
            nullable=True,
            comment="SHA-256 Hash der festgeschriebenen Daten"
        ),

        # Sync-Status
        sa.Column(
            "sync_status",
            sa.String(20),
            nullable=False,
            default="pending",
            comment="Sync-Status: pending, synced, failed, conflict"
        ),
        sa.Column(
            "datev_buchung_id",
            sa.String(50),
            nullable=True,
            comment="ID in DATEV nach Sync"
        ),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Zeitpunkt des Syncs"
        ),
        sa.Column(
            "sync_error",
            sa.Text(),
            nullable=True,
            comment="Fehlermeldung bei Sync-Fehler"
        ),
        sa.Column(
            "retry_count",
            sa.Integer(),
            nullable=False,
            default=0,
            comment="Anzahl Sync-Versuche"
        ),

        # Kontierungsvorschlag-Metadaten
        sa.Column(
            "suggestion_confidence",
            sa.Float(),
            nullable=True,
            comment="Konfidenz des Kontierungsvorschlags (0-1)"
        ),
        sa.Column(
            "suggestion_source",
            sa.String(20),
            nullable=True,
            comment="Quelle: rule, ml, manual"
        ),
        sa.Column(
            "original_suggestion_konto",
            sa.String(10),
            nullable=True,
            comment="Urspruenglicher Kontovorschlag"
        ),
        sa.Column(
            "original_suggestion_gegenkonto",
            sa.String(10),
            nullable=True,
            comment="Urspruenglicher Gegenkontovorschlag"
        ),
        sa.Column(
            "user_korrektur",
            sa.Boolean(),
            nullable=False,
            default=False,
            comment="Vom User korrigiert (fuer ML-Training)"
        ),

        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True
        ),

        # Constraints
        sa.CheckConstraint(
            "soll_haben IN ('S', 'H')",
            name="ck_datev_buchung_soll_haben"
        ),
        sa.CheckConstraint(
            "sync_status IN ('pending', 'synced', 'failed', 'conflict')",
            name="ck_datev_buchung_sync_status"
        ),
        sa.CheckConstraint(
            "umsatz > 0",
            name="ck_datev_buchung_umsatz_positiv"
        ),

        # GoBD: Festgeschriebene Buchungen duerfen nicht geaendert werden
        # (Business Logic Constraint - wird in Service Layer geprueft)
    )

    # Indexes fuer datev_buchungen
    op.create_index(
        "ix_datev_buchungen_connection",
        "datev_buchungen",
        ["connection_id"]
    )
    op.create_index(
        "ix_datev_buchungen_document",
        "datev_buchungen",
        ["document_id"]
    )
    op.create_index(
        "ix_datev_buchungen_company",
        "datev_buchungen",
        ["company_id"]
    )
    op.create_index(
        "ix_datev_buchungen_belegdatum",
        "datev_buchungen",
        ["belegdatum"]
    )
    op.create_index(
        "ix_datev_buchungen_konto",
        "datev_buchungen",
        ["konto"]
    )
    op.create_index(
        "ix_datev_buchungen_gegenkonto",
        "datev_buchungen",
        ["gegenkonto"]
    )
    op.create_index(
        "ix_datev_buchungen_sync_status",
        "datev_buchungen",
        ["sync_status"]
    )
    op.create_index(
        "ix_datev_buchungen_festgeschrieben",
        "datev_buchungen",
        ["ist_festgeschrieben"]
    )
    op.create_index(
        "ix_datev_buchungen_guid",
        "datev_buchungen",
        ["buchungs_guid"],
        unique=True
    )

    # Composite Index fuer Periodenabfragen
    op.create_index(
        "ix_datev_buchungen_period",
        "datev_buchungen",
        ["connection_id", "belegdatum"]
    )

    # ==========================================================================
    # 4. DATEV Beleglinks - Verknuepfung Buchung <-> Beleg
    # ==========================================================================
    op.create_table(
        "datev_beleglinks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "buchung_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("datev_buchungen.id", ondelete="CASCADE"),
            nullable=False
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
            nullable=True
        ),

        # Beleglink-Daten
        sa.Column(
            "beleglink_url",
            sa.String(2000),
            nullable=False,
            comment="Vollstaendige URL zum Beleg"
        ),
        sa.Column(
            "beleglink_guid",
            sa.String(36),
            nullable=False,
            comment="DATEV Beleglink-GUID"
        ),

        # Upload-Status
        sa.Column(
            "upload_status",
            sa.String(20),
            nullable=False,
            default="pending",
            comment="Upload-Status: pending, uploaded, failed"
        ),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            nullable=True
        ),
        sa.Column(
            "datev_document_id",
            sa.String(50),
            nullable=True,
            comment="ID in DATEV Belegarchiv"
        ),
        sa.Column(
            "upload_error",
            sa.Text(),
            nullable=True
        ),

        # Metadaten
        sa.Column(
            "mime_type",
            sa.String(100),
            nullable=True
        ),
        sa.Column(
            "file_size",
            sa.Integer(),
            nullable=True
        ),
        sa.Column(
            "checksum_sha256",
            sa.String(64),
            nullable=True,
            comment="SHA-256 Hash der Datei"
        ),

        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False
        ),

        # Constraints
        sa.CheckConstraint(
            "upload_status IN ('pending', 'uploaded', 'failed')",
            name="ck_datev_beleglink_status"
        ),

        # Unique: Ein Beleg pro Buchung (1:1)
        sa.UniqueConstraint(
            "buchung_id", "beleglink_guid",
            name="uq_datev_beleglink"
        ),
    )

    # Indexes fuer datev_beleglinks
    op.create_index(
        "ix_datev_beleglinks_buchung",
        "datev_beleglinks",
        ["buchung_id"]
    )
    op.create_index(
        "ix_datev_beleglinks_document",
        "datev_beleglinks",
        ["document_id"]
    )
    op.create_index(
        "ix_datev_beleglinks_status",
        "datev_beleglinks",
        ["upload_status"]
    )

    # ==========================================================================
    # 5. DATEV Kontierung Patterns - ML-basierte Vorschlaege
    # ==========================================================================
    op.create_table(
        "datev_kontierung_patterns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("datev_connections.id", ondelete="CASCADE"),
            nullable=False
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False
        ),

        # Matching-Kriterien
        sa.Column(
            "entity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("business_entities.id", ondelete="SET NULL"),
            nullable=True,
            comment="Optionale Zuordnung zu Geschaeftspartner"
        ),
        sa.Column(
            "entity_name_pattern",
            sa.String(200),
            nullable=True,
            comment="Fuzzy-Match Pattern fuer Firmennamen"
        ),
        sa.Column(
            "document_type",
            sa.String(50),
            nullable=True,
            comment="Dokumenttyp: invoice, credit_note, receipt, etc."
        ),
        sa.Column(
            "amount_range_min",
            sa.Numeric(15, 2),
            nullable=True,
            comment="Minimaler Betrag fuer Match"
        ),
        sa.Column(
            "amount_range_max",
            sa.Numeric(15, 2),
            nullable=True,
            comment="Maximaler Betrag fuer Match"
        ),
        sa.Column(
            "text_keywords",
            postgresql.JSONB,
            nullable=True,
            comment="Stichwort-Array fuer Textmatching"
        ),

        # Resultierende Kontierung
        sa.Column(
            "konto",
            sa.String(10),
            nullable=False,
            comment="Vorgeschlagenes Konto"
        ),
        sa.Column(
            "gegenkonto",
            sa.String(10),
            nullable=False,
            comment="Vorgeschlagenes Gegenkonto"
        ),
        sa.Column(
            "bu_schluessel",
            sa.String(5),
            nullable=True,
            comment="Vorgeschlagener Steuerschluessel"
        ),
        sa.Column(
            "kostenstelle",
            sa.String(20),
            nullable=True,
            comment="Vorgeschlagene Kostenstelle"
        ),

        # Statistik
        sa.Column(
            "usage_count",
            sa.Integer(),
            nullable=False,
            default=0,
            comment="Anzahl Verwendungen"
        ),
        sa.Column(
            "success_count",
            sa.Integer(),
            nullable=False,
            default=0,
            comment="Anzahl erfolgreiche Verwendungen (ohne Korrektur)"
        ),
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            nullable=True
        ),

        # Machine Learning Metadaten
        sa.Column(
            "feature_vector",
            postgresql.JSONB,
            nullable=True,
            comment="Feature-Vektor fuer ML-Matching"
        ),
        sa.Column(
            "model_version",
            sa.String(20),
            nullable=True,
            comment="Version des ML-Modells"
        ),
        sa.Column(
            "pattern_source",
            sa.String(20),
            nullable=False,
            default="manual",
            comment="Quelle: manual, learned, imported"
        ),

        # Status
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            default=True
        ),
        sa.Column(
            "priority",
            sa.Integer(),
            nullable=False,
            default=0,
            comment="Prioritaet bei Mehrfach-Match (hoeher = besser)"
        ),

        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False
        ),

        # Constraints
        sa.CheckConstraint(
            "pattern_source IN ('manual', 'learned', 'imported')",
            name="ck_datev_pattern_source"
        ),
    )

    # Indexes fuer datev_kontierung_patterns
    op.create_index(
        "ix_datev_patterns_connection",
        "datev_kontierung_patterns",
        ["connection_id"]
    )
    op.create_index(
        "ix_datev_patterns_company",
        "datev_kontierung_patterns",
        ["company_id"]
    )
    op.create_index(
        "ix_datev_patterns_entity",
        "datev_kontierung_patterns",
        ["entity_id"]
    )
    op.create_index(
        "ix_datev_patterns_active",
        "datev_kontierung_patterns",
        ["is_active"]
    )
    op.create_index(
        "ix_datev_patterns_konto",
        "datev_kontierung_patterns",
        ["konto", "gegenkonto"]
    )

    # GIN Index fuer Text-Keyword-Suche
    op.create_index(
        "ix_datev_patterns_keywords",
        "datev_kontierung_patterns",
        ["text_keywords"],
        postgresql_using="gin"
    )

    # ==========================================================================
    # 6. DATEV Sync History - Protokoll aller Synchronisationen
    # ==========================================================================
    op.create_table(
        "datev_sync_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("datev_connections.id", ondelete="CASCADE"),
            nullable=False
        ),

        # Sync-Details
        sa.Column(
            "sync_type",
            sa.String(30),
            nullable=False,
            comment="Sync-Typ: stammdaten, kontenplan, buchungen, belege, full"
        ),
        sa.Column(
            "sync_direction",
            sa.String(20),
            nullable=False,
            comment="Richtung: push, pull, bidirectional"
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            comment="Status: running, success, failed, partial"
        ),

        # Statistik
        sa.Column(
            "records_total",
            sa.Integer(),
            nullable=False,
            default=0
        ),
        sa.Column(
            "records_created",
            sa.Integer(),
            nullable=False,
            default=0
        ),
        sa.Column(
            "records_updated",
            sa.Integer(),
            nullable=False,
            default=0
        ),
        sa.Column(
            "records_failed",
            sa.Integer(),
            nullable=False,
            default=0
        ),
        sa.Column(
            "records_skipped",
            sa.Integer(),
            nullable=False,
            default=0
        ),

        # Timing
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True
        ),
        sa.Column(
            "duration_seconds",
            sa.Float(),
            nullable=True
        ),

        # Fehlerdetails
        sa.Column(
            "error_message",
            sa.Text(),
            nullable=True
        ),
        sa.Column(
            "error_details",
            postgresql.JSONB,
            nullable=True,
            comment="Detaillierte Fehlerinformationen"
        ),
        sa.Column(
            "failed_records",
            postgresql.JSONB,
            nullable=True,
            comment="Liste fehlgeschlagener Datensaetze"
        ),

        # Trigger
        sa.Column(
            "triggered_by",
            sa.String(50),
            nullable=True,
            comment="Ausloeser: manual, scheduled, webhook, api"
        ),
        sa.Column(
            "triggered_by_user",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True
        ),
        sa.Column(
            "celery_task_id",
            sa.String(50),
            nullable=True,
            comment="Celery Task ID"
        ),

        # Constraints
        sa.CheckConstraint(
            "sync_type IN ('stammdaten', 'kontenplan', 'buchungen', 'belege', 'full')",
            name="ck_datev_sync_type"
        ),
        sa.CheckConstraint(
            "sync_direction IN ('push', 'pull', 'bidirectional')",
            name="ck_datev_sync_direction"
        ),
        sa.CheckConstraint(
            "status IN ('running', 'success', 'failed', 'partial', 'cancelled')",
            name="ck_datev_sync_status"
        ),
    )

    # Indexes fuer datev_sync_history
    op.create_index(
        "ix_datev_sync_history_connection",
        "datev_sync_history",
        ["connection_id"]
    )
    op.create_index(
        "ix_datev_sync_history_type",
        "datev_sync_history",
        ["sync_type"]
    )
    op.create_index(
        "ix_datev_sync_history_status",
        "datev_sync_history",
        ["status"]
    )
    op.create_index(
        "ix_datev_sync_history_started",
        "datev_sync_history",
        ["started_at"]
    )


def downgrade() -> None:
    """Entfernt DATEV Connect Tabellen."""

    # Reihenfolge beachten wegen Foreign Keys
    op.drop_table("datev_sync_history")
    op.drop_table("datev_kontierung_patterns")
    op.drop_table("datev_beleglinks")
    op.drop_table("datev_buchungen")
    op.drop_table("datev_kontenplan")
    op.drop_table("datev_connections")
