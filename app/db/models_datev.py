"""DATEV domain models - ausgelagert aus models.py (Modularisierung Phase 1.1).

Enthaelt alle SQLAlchemy-Modelle fuer den DATEV-Export und DATEV-Connect.
"""

import uuid
from enum import Enum

from sqlalchemy import (
    Boolean, CheckConstraint, Column, Date, DateTime, Float,
    ForeignKey, Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models_base import Base, CrossDBJSON


# =============================================================================
# DATEV EXPORT MODELS
# =============================================================================


class DATEVConfiguration(Base):
    """
    DATEV Export Konfiguration.

    Speichert Steuerberater-Zugangsdaten und Konteneinstellungen
    für den DATEV Buchungsstapel-Export.

    Jeder Benutzer kann mehrere Konfigurationen haben (z.B. für verschiedene
    Mandanten oder Testumgebungen).
    """

    __tablename__ = "datev_configurations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        comment="Benutzer-spezifische Konfiguration"
    )

    # DATEV Pflichtfelder
    berater_nr = Column(
        String(7),
        nullable=False,
        comment="Beraternummer (max. 7-stellig)"
    )
    mandanten_nr = Column(
        String(5),
        nullable=False,
        comment="Mandantennummer (max. 5-stellig)"
    )
    wj_beginn = Column(
        Date,
        nullable=False,
        comment="Wirtschaftsjahr-Beginn"
    )

    # Kontenrahmen
    kontenrahmen = Column(
        String(10),
        nullable=False,
        default="SKR03",
        comment="SKR03 oder SKR04"
    )

    # Standardkonten Eingangsrechnungen
    incoming_expense_account = Column(
        String(10),
        nullable=True,
        comment="Aufwandskonto Eingang (z.B. 4200)"
    )
    incoming_creditor_account = Column(
        String(10),
        nullable=True,
        comment="Kreditorenkonto Eingang (z.B. 70000)"
    )

    # Standardkonten Ausgangsrechnungen
    outgoing_revenue_account = Column(
        String(10),
        nullable=True,
        comment="Erloeskonto Ausgang (z.B. 8400)"
    )
    outgoing_debtor_account = Column(
        String(10),
        nullable=True,
        comment="Debitorenkonto Ausgang (z.B. 10000)"
    )

    # Sammelkonten
    sammelkonto_kreditoren = Column(
        String(10),
        default="1600",
        comment="Sammelkonto Kreditoren"
    )
    sammelkonto_debitoren = Column(
        String(10),
        default="1400",
        comment="Sammelkonto Debitoren"
    )

    # Optionale Einstellungen
    sachkontenlange = Column(
        Integer,
        default=4,
        comment="Länge Sachkonten (4-8 Stellen)"
    )
    buchungstext_format = Column(
        String(100),
        default="{invoice_number}",
        comment="Format für Buchungstext"
    )

    # Status
    is_default = Column(Boolean, default=False, comment="Standard-Konfiguration")
    is_active = Column(Boolean, default=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", backref="datev_configurations")
    vendor_mappings = relationship(
        "DATEVVendorMapping",
        back_populates="config",
        cascade="all, delete-orphan"
    )
    exports = relationship(
        "DATEVExport",
        back_populates="config",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_datev_configurations_user_id", "user_id"),
        Index("ix_datev_configurations_is_default", "is_default"),
        Index("ix_datev_configurations_is_active", "is_active"),
        CheckConstraint(
            "kontenrahmen IN ('SKR03', 'SKR04')",
            name="ck_datev_config_kontenrahmen"
        ),
        CheckConstraint(
            "sachkontenlange BETWEEN 4 AND 8",
            name="ck_datev_config_sachkontenlange"
        ),
    )


class DATEVVendorMapping(Base):
    """
    Lieferanten-spezifische Kontozuordnung.

    Ermöglicht individuelle Konten pro Lieferant statt Standardkonten.
    Matching erfolgt über verschiedene Kriterien (Name, USt-IdNr, IBAN, Entity).
    """

    __tablename__ = "datev_vendor_mappings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    config_id = Column(
        UUID(as_uuid=True),
        ForeignKey("datev_configurations.id", ondelete="CASCADE"),
        nullable=False
    )

    # Lieferanten-Identifikation (mehrere Match-Optionen)
    vendor_name = Column(
        String(255),
        nullable=True,
        comment="Firmenname (Fuzzy-Match)"
    )
    vendor_vat_id = Column(
        String(50),
        nullable=True,
        comment="USt-IdNr (exakter Match)"
    )
    vendor_iban = Column(
        String(34),
        nullable=True,
        comment="IBAN (exakter Match)"
    )
    business_entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="SET NULL"),
        nullable=True,
        comment="Verknüpfter Geschäftspartner"
    )

    # Kontozuordnung
    expense_account = Column(
        String(10),
        nullable=False,
        comment="Aufwandskonto"
    )
    creditor_account = Column(
        String(10),
        nullable=True,
        comment="Personenkonto (Kreditor)"
    )
    cost_center = Column(
        String(20),
        nullable=True,
        comment="Kostenstelle"
    )
    cost_object = Column(
        String(20),
        nullable=True,
        comment="Kostentraeger"
    )

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    config = relationship("DATEVConfiguration", back_populates="vendor_mappings")
    business_entity = relationship("BusinessEntity", backref="datev_vendor_mappings")

    __table_args__ = (
        Index("ix_datev_vendor_mappings_config_id", "config_id"),
        Index("ix_datev_vendor_mappings_vendor_vat_id", "vendor_vat_id"),
        Index("ix_datev_vendor_mappings_vendor_iban", "vendor_iban"),
        Index("ix_datev_vendor_mappings_business_entity_id", "business_entity_id"),
    )


class DATEVExport(Base):
    """
    DATEV Export Historie.

    Protokolliert alle Exporte für Audit und Nachvollziehbarkeit.
    Speichert welche Dokumente wann in welchen Export einbezogen wurden.
    """

    __tablename__ = "datev_exports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    config_id = Column(
        UUID(as_uuid=True),
        ForeignKey("datev_configurations.id", ondelete="CASCADE"),
        nullable=False
    )
    exported_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Export-Details
    export_type = Column(
        String(50),
        nullable=False,
        default="buchungsstapel",
        comment="buchungsstapel, stammdaten"
    )
    filename = Column(String(255), nullable=False)
    document_count = Column(Integer, default=0)

    # Zeitraum
    period_from = Column(Date, nullable=True)
    period_to = Column(Date, nullable=True)

    # Datei-Metadaten
    content_hash = Column(
        String(64),
        nullable=True,
        comment="SHA256 der Export-Datei"
    )
    file_size_bytes = Column(Integer, nullable=True)

    # Status
    status = Column(
        String(20),
        default="completed",
        comment="completed, failed, partial"
    )
    error_message = Column(Text, nullable=True)

    # Inkludierte Dokumente
    included_documents = Column(
        CrossDBJSON,
        nullable=True,
        default=list,
        comment="Array von Dokument-UUIDs"
    )
    skipped_documents = Column(
        CrossDBJSON,
        nullable=True,
        default=list,
        comment="Array von übersprungenen Dokument-UUIDs"
    )
    warnings = Column(
        CrossDBJSON,
        nullable=True,
        default=list,
        comment="Array von Warnmeldungen"
    )

    # Audit
    exported_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    config = relationship("DATEVConfiguration", back_populates="exports")
    exported_by = relationship("User", backref="datev_exports")

    __table_args__ = (
        Index("ix_datev_exports_config_id", "config_id"),
        Index("ix_datev_exports_exported_by_id", "exported_by_id"),
        Index("ix_datev_exports_exported_at", "exported_at"),
        Index("ix_datev_exports_period", "period_from", "period_to"),
        Index("ix_datev_exports_status", "status"),
        CheckConstraint(
            "status IN ('completed', 'failed', 'partial')",
            name="ck_datev_exports_status"
        ),
    )


# =============================================================================
# DATEV CONNECT INTEGRATION (Migration 145)
# =============================================================================


class DATEVConnectionStatus(str, Enum):
    """DATEV Connection Status."""
    pending = "pending"
    connecting = "connecting"
    connected = "connected"
    disconnected = "disconnected"
    error = "error"
    token_expired = "token_expired"


class DATEVSyncType(str, Enum):
    """DATEV Sync Operation Types."""
    stammdaten_push = "stammdaten_push"
    stammdaten_pull = "stammdaten_pull"
    buchungsstapel = "buchungsstapel"
    belegbilder = "belegbilder"
    kontierung = "kontierung"
    kontenplan = "kontenplan"


class DATEVKontierungStatus(str, Enum):
    """Status of Kontierung Suggestion."""
    suggested = "suggested"
    accepted = "accepted"
    rejected = "rejected"
    modified = "modified"


class DATEVConnection(Base):
    """
    DATEVconnect API Connection.

    Verwaltet OAuth2-Verbindung zu DATEVconnect für bidirektionale Synchronisation.
    Unterstützt Buchungsstapel, Belegbilder und Stammdaten-Sync.

    SECURITY: Alle Credentials werden verschluesselt gespeichert (AES-256-GCM).
    """

    __tablename__ = "datev_connections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        comment="Multi-Tenant Isolation"
    )
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Ersteller der Verbindung"
    )

    # Connection Name
    name = Column(String(100), nullable=False, comment="Anzeigename der Verbindung")
    description = Column(Text, nullable=True)

    # DATEV Identifiers
    mandant_nr = Column(String(10), nullable=False, comment="DATEV Mandantennummer")
    berater_nr = Column(String(10), nullable=False, comment="DATEV Beraternummer")
    kontenrahmen = Column(
        String(10),
        nullable=False,
        default="SKR03",
        comment="Kontenrahmen (SKR03/SKR04)"
    )
    wirtschaftsjahr_beginn = Column(
        Integer,
        nullable=False,
        default=1,
        comment="Monat des Wirtschaftsjahresbeginns (1-12)"
    )

    # OAuth2 Credentials (encrypted)
    client_id = Column(String(100), nullable=True)
    client_secret_encrypted = Column(Text, nullable=True, comment="AES-256-GCM encrypted")
    access_token_encrypted = Column(Text, nullable=True, comment="AES-256-GCM encrypted")
    refresh_token_encrypted = Column(Text, nullable=True, comment="AES-256-GCM encrypted")
    token_expires_at = Column(DateTime(timezone=True), nullable=True)

    # Connection Configuration
    environment = Column(
        String(20),
        nullable=False,
        default="production",
        comment="production or sandbox"
    )
    api_version = Column(String(10), nullable=True, default="v1")
    webhook_url = Column(String(500), nullable=True, comment="Callback URL for notifications")

    # Sync Configuration
    auto_kontierung = Column(Boolean, default=False, comment="Automatische Kontierungsvorschläge")
    auto_beleg_upload = Column(Boolean, default=True, comment="Automatischer Belegbilder-Upload")
    sync_interval_minutes = Column(Integer, default=60, comment="Sync-Intervall in Minuten")
    last_buchung_nr = Column(Integer, nullable=True, comment="Letzte verwendete Buchungsnummer")

    # Status
    connection_status = Column(
        String(20),
        nullable=False,
        default="pending",
        comment="pending, connecting, connected, disconnected, error, token_expired"
    )
    last_connection_at = Column(DateTime(timezone=True), nullable=True)
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)

    # Audit
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    company = relationship("Company", backref="datev_connections")
    created_by = relationship("User", backref="datev_connections_created")
    buchungen = relationship("DATEVBuchung", back_populates="connection", cascade="all, delete-orphan")
    sync_history = relationship("DATEVSyncHistory", back_populates="connection", cascade="all, delete-orphan")
    kontenplan = relationship("DATEVKontenplan", back_populates="connection", cascade="all, delete-orphan")
    beleglinks = relationship("DATEVBeleglink", back_populates="connection", cascade="all, delete-orphan")
    kontierung_patterns = relationship("DATEVKontierungPattern", back_populates="connection", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_datev_connections_company_id", "company_id"),
        Index("ix_datev_connections_mandant_berater", "mandant_nr", "berater_nr"),
        Index("ix_datev_connections_status", "connection_status"),
        UniqueConstraint("company_id", "mandant_nr", "berater_nr", name="uq_datev_connection_per_mandant"),
    )


class DATEVKontenplan(Base):
    """
    DATEV Kontenplan Cache.

    Lokaler Cache des DATEV Kontenplans für schnelle Kontierungsvorschläge.
    Wird periodisch mit DATEV synchronisiert.
    """

    __tablename__ = "datev_kontenplan"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("datev_connections.id", ondelete="CASCADE"),
        nullable=False
    )

    # Konto
    kontonummer = Column(String(10), nullable=False, comment="Kontennummer (z.B. 4400)")
    bezeichnung = Column(String(200), nullable=False, comment="Kontobezeichnung")
    kontenrahmen = Column(String(10), nullable=False, comment="SKR03 oder SKR04")
    kontotyp = Column(
        String(50),
        nullable=True,
        comment="sachkonto, personenkonto, erloes, aufwand, etc."
    )

    # Steuer
    steuerschluessel_default = Column(String(5), nullable=True, comment="Standard-Steuerschluessel")
    mwst_satz = Column(Float, nullable=True, comment="Standard-MwSt-Satz")

    # Hierarchie
    kontenklasse = Column(Integer, nullable=True, comment="0-9 Kontenklasse")
    is_sammelkonto = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    # Sync
    synced_at = Column(DateTime(timezone=True), nullable=True)
    datev_konto_id = Column(String(50), nullable=True, comment="DATEV interne ID")

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    connection = relationship("DATEVConnection", back_populates="kontenplan")

    __table_args__ = (
        Index("ix_datev_kontenplan_connection_id", "connection_id"),
        Index("ix_datev_kontenplan_kontonummer", "kontonummer"),
        Index("ix_datev_kontenplan_lookup", "connection_id", "kontonummer", "kontenrahmen"),
        UniqueConstraint("connection_id", "kontonummer", name="uq_datev_konto_per_connection"),
    )


class DATEVBuchung(Base):
    """
    DATEV Buchungssatz.

    Repraesentiert einen Buchungssatz für den DATEV Export.
    GoBD-konform mit SHA-256 Hash für Unveränderbarkeit nach Festschreibung.

    SECURITY: Festgeschriebene Buchungen sind immutable (gobd_festgeschrieben=True).
    """

    __tablename__ = "datev_buchungen"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("datev_connections.id", ondelete="CASCADE"),
        nullable=False
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Multi-Tenant Isolation (in der Doppik-Refactor faelschlich entfernt)"
    )
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        comment="Verknüpftes Quelldokument"
    )
    entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="SET NULL"),
        nullable=True,
        comment="Verknüpfter Geschäftspartner"
    )

    # Buchungssatz
    buchungsnummer = Column(Integer, nullable=True, comment="Fortlaufende Nummer im Stapel")
    belegdatum = Column(Date, nullable=False, comment="Datum des Belegs")
    buchungsdatum = Column(Date, nullable=True, comment="Datum der Buchung")
    valutadatum = Column(Date, nullable=True, comment="Valutadatum")

    # Betraege
    betrag_soll = Column(Float, nullable=False, comment="Soll-Betrag (immer positiv)")
    betrag_haben = Column(Float, nullable=False, comment="Haben-Betrag (immer positiv)")
    waehrung = Column(String(3), nullable=False, default="EUR")

    # Konten
    konto_soll = Column(String(10), nullable=False, comment="Soll-Konto")
    konto_haben = Column(String(10), nullable=False, comment="Haben-Konto")
    steuerschluessel = Column(String(5), nullable=True, comment="DATEV Steuerschluessel")
    kostenstelle_1 = Column(String(20), nullable=True)
    kostenstelle_2 = Column(String(20), nullable=True)
    kostentraeger = Column(String(20), nullable=True)

    # Buchungstext
    buchungstext = Column(String(120), nullable=True, comment="Buchungstext (max 120 Zeichen)")
    belegnummer = Column(String(36), nullable=True, comment="Belegnummer/Rechnungsnummer")

    # GoBD Compliance
    gobd_festgeschrieben = Column(
        Boolean,
        default=False,
        comment="True = unveränderbar (GoBD-konform)"
    )
    gobd_hash = Column(String(64), nullable=True, comment="SHA-256 Hash für Unveränderbarkeit")
    festgeschrieben_at = Column(DateTime(timezone=True), nullable=True)
    festgeschrieben_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Sync Status
    sync_status = Column(
        String(20),
        nullable=False,
        default="pending",
        comment="pending, synced, error"
    )
    synced_at = Column(DateTime(timezone=True), nullable=True)
    datev_buchung_id = Column(String(50), nullable=True, comment="ID nach DATEV-Sync")
    sync_error = Column(Text, nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Relationships
    connection = relationship("DATEVConnection", back_populates="buchungen")
    document = relationship("Document", backref="datev_buchungen")
    entity = relationship("BusinessEntity", backref="datev_buchungen")

    __table_args__ = (
        Index("ix_datev_buchungen_connection_id", "connection_id"),
        Index("ix_datev_buchungen_document_id", "document_id"),
        Index("ix_datev_buchungen_entity_id", "entity_id"),
        Index("ix_datev_buchungen_belegdatum", "belegdatum"),
        Index("ix_datev_buchungen_sync_status", "sync_status"),
        Index("ix_datev_buchungen_gobd", "gobd_festgeschrieben"),
        CheckConstraint(
            "sync_status IN ('pending', 'synced', 'error')",
            name="ck_datev_buchungen_sync_status"
        ),
    )


class DATEVBeleglink(Base):
    """
    DATEV Belegbild-Verknüpfung.

    Verknüpft hochgeladene Belegbilder mit DATEV-Buchungen.
    Ermöglicht den Upload zu DATEV Unternehmen Online (DUO).
    """

    __tablename__ = "datev_beleglinks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("datev_connections.id", ondelete="CASCADE"),
        nullable=False
    )
    buchung_id = Column(
        UUID(as_uuid=True),
        ForeignKey("datev_buchungen.id", ondelete="CASCADE"),
        nullable=True,
        comment="Verknüpfte Buchung"
    )
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        comment="Quelldokument mit Belegbild"
    )

    # Upload Status
    upload_status = Column(
        String(20),
        nullable=False,
        default="pending",
        comment="pending, uploaded, error"
    )
    uploaded_at = Column(DateTime(timezone=True), nullable=True)
    datev_beleg_id = Column(String(100), nullable=True, comment="DATEV Beleg-ID nach Upload")
    upload_error = Column(Text, nullable=True)

    # File Info
    original_filename = Column(String(255), nullable=True)
    file_hash = Column(String(64), nullable=True, comment="SHA-256 des Belegbilds")
    file_size_bytes = Column(Integer, nullable=True)
    mime_type = Column(String(100), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    connection = relationship("DATEVConnection", back_populates="beleglinks")
    buchung = relationship("DATEVBuchung", backref="beleglinks")
    document = relationship("Document", backref="datev_beleglinks")

    __table_args__ = (
        Index("ix_datev_beleglinks_connection_id", "connection_id"),
        Index("ix_datev_beleglinks_buchung_id", "buchung_id"),
        Index("ix_datev_beleglinks_document_id", "document_id"),
        Index("ix_datev_beleglinks_upload_status", "upload_status"),
        CheckConstraint(
            "upload_status IN ('pending', 'uploaded', 'error')",
            name="ck_datev_beleglinks_upload_status"
        ),
    )


class DATEVKontierungPattern(Base):
    """
    ML-basierte Kontierungsmuster.

    Lernt aus historischen Buchungen und User-Korrekturen um
    intelligente Kontierungsvorschläge zu generieren.

    Matching-Kriterien: Lieferant, Betrag-Range, Stichwort.
    """

    __tablename__ = "datev_kontierung_patterns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("datev_connections.id", ondelete="CASCADE"),
        nullable=False
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Multi-Tenant Isolation (in der Doppik-Refactor faelschlich entfernt)"
    )

    # Matching-Kriterien
    entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=True,
        comment="Optionaler Geschäftspartner-Match"
    )
    pattern_type = Column(
        String(50),
        nullable=False,
        comment="entity, keyword, amount_range, document_type"
    )
    keyword_pattern = Column(String(200), nullable=True, comment="Regex-Pattern für Buchungstext")
    amount_min = Column(Float, nullable=True)
    amount_max = Column(Float, nullable=True)
    document_type = Column(String(50), nullable=True, comment="Dokumenttyp-Filter")

    # Kontierung
    konto_soll = Column(String(10), nullable=False)
    konto_haben = Column(String(10), nullable=False)
    steuerschluessel = Column(String(5), nullable=True)
    kostenstelle = Column(String(20), nullable=True)

    # ML Metrics
    confidence = Column(Float, nullable=False, default=0.5, comment="0.0-1.0 Konfidenz")
    usage_count = Column(Integer, default=0, comment="Wie oft wurde dieses Pattern verwendet")
    success_count = Column(Integer, default=0, comment="Wie oft wurde es akzeptiert")
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    # Status
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    connection = relationship("DATEVConnection", back_populates="kontierung_patterns")
    entity = relationship("BusinessEntity", backref="datev_kontierung_patterns")

    __table_args__ = (
        Index("ix_datev_kontierung_patterns_connection_id", "connection_id"),
        Index("ix_datev_kontierung_patterns_entity_id", "entity_id"),
        Index("ix_datev_kontierung_patterns_confidence", "confidence"),
        Index("ix_datev_kontierung_patterns_lookup", "connection_id", "entity_id", "pattern_type"),
    )


class DATEVSyncHistory(Base):
    """
    DATEV Sync-Historie.

    Protokolliert alle Sync-Operationen für Audit und Debugging.
    """

    __tablename__ = "datev_sync_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("datev_connections.id", ondelete="CASCADE"),
        nullable=False
    )
    triggered_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Sync Details
    sync_type = Column(
        String(50),
        nullable=False,
        comment="stammdaten_push, stammdaten_pull, buchungsstapel, belegbilder, kontierung, kontenplan"
    )
    direction = Column(String(10), nullable=False, default="push", comment="push or pull")

    # Results
    status = Column(
        String(20),
        nullable=False,
        default="running",
        comment="running, completed, partial, failed"
    )
    items_total = Column(Integer, default=0)
    items_success = Column(Integer, default=0)
    items_failed = Column(Integer, default=0)
    items_skipped = Column(Integer, default=0)

    # Timing
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Float, nullable=True)

    # Error Handling
    error_message = Column(Text, nullable=True)
    error_details = Column(CrossDBJSON, nullable=True, default=dict)

    # Metadata
    sync_metadata = Column(CrossDBJSON, nullable=True, default=dict, comment="Zusätzliche Sync-Infos")  # Renamed: 'metadata' is reserved in SQLAlchemy

    # Relationships
    connection = relationship("DATEVConnection", back_populates="sync_history")
    user = relationship("User", backref="datev_sync_triggered")

    __table_args__ = (
        Index("ix_datev_sync_history_connection_id", "connection_id"),
        Index("ix_datev_sync_history_started_at", "started_at"),
        Index("ix_datev_sync_history_status", "status"),
        Index("ix_datev_sync_history_sync_type", "sync_type"),
        CheckConstraint(
            "status IN ('running', 'completed', 'partial', 'failed')",
            name="ck_datev_sync_history_status"
        ),
        CheckConstraint(
            "direction IN ('push', 'pull')",
            name="ck_datev_sync_history_direction"
        ),
    )


# =============================================================================
# FINANCE DOCUMENT HISTORY
# =============================================================================


class FinanceDocumentHistory(Base):
    """Immutable Audit-Log für Finanz-Dokumente.

    Trackt alle Änderungen an Finanz-Dokumenten für Enterprise-Compliance:
    - Erstellung, Bearbeitung, Löschung
    - Kategorie- und Jahr-Änderungen
    - Frist-Änderungen
    - OCR-Verarbeitung

    WICHTIG: Diese Tabelle ist append-only!
    Ein Datenbank-Trigger sollte UPDATE und DELETE verhindern.
    """
    __tablename__ = "finance_document_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Dokument-Referenz
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Benutzer, der die Änderung vorgenommen hat
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    # Aktion
    action = Column(
        String(50),
        nullable=False,
        comment="created, updated, deleted, restored, category_changed, year_changed, etc."
    )

    # Änderungsdetails
    old_values = Column(
        CrossDBJSON,
        nullable=True,
        default=dict,
        comment="Vorherige Werte (bei Updates)"
    )
    new_values = Column(
        CrossDBJSON,
        nullable=True,
        default=dict,
        comment="Neue Werte (bei Updates)"
    )

    # Betroffene Felder
    changed_fields = Column(
        CrossDBJSON,
        nullable=True,
        default=list,
        comment="Liste der geänderten Felder"
    )

    # Kontext
    ip_address = Column(String(45), nullable=True, comment="IP-Adresse des Benutzers")
    user_agent = Column(String(500), nullable=True, comment="Browser/Client Info")

    # Zusätzliche Metadaten
    # Note: DB column is 'metadata', but we use 'extra_metadata' as Python attribute
    # because 'metadata' is reserved in SQLAlchemy's Declarative API
    extra_metadata = Column(
        'metadata',  # Actual DB column name
        CrossDBJSON,
        nullable=True,
        default=dict,
        comment="Zusätzliche Kontext-Informationen"
    )

    # Beschreibung (menschenlesbar, auf Deutsch)
    description = Column(
        Text,
        nullable=True,
        comment="Menschenlesbare Beschreibung der Änderung"
    )

    # Zeitstempel (immutable)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    document = relationship("Document", backref="finance_history")
    user = relationship("User", backref="finance_document_changes")

    # Indexes
    __table_args__ = (
        Index("ix_finance_doc_history_document_id", "document_id"),
        Index("ix_finance_doc_history_user_id", "user_id"),
        Index("ix_finance_doc_history_action", "action"),
        Index("ix_finance_doc_history_created_at", "created_at"),
        Index("ix_finance_doc_history_doc_created", "document_id", "created_at"),
        CheckConstraint(
            "action IN ('created', 'updated', 'deleted', 'restored', "
            "'category_changed', 'year_changed', 'ocr_completed', "
            "'deadline_set', 'deadline_removed', 'bulk_update')",
            name="ck_finance_doc_history_action"
        ),
    )
