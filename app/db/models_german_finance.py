# -*- coding: utf-8 -*-
"""
Deutsche Finanz-Feature Datenbankmodelle.

Modelle für:
- USt-Voranmeldung (Umsatzsteuer-Voranmeldung)
- BWA (Betriebswirtschaftliche Auswertung)
- Cashflow-Prognose mit Szenarien

Feature #11: Deutsche Finanz-Features
Feinpoliert und durchdacht - Enterprise-grade Deutsche Finanzberichterstattung.
"""

import uuid
from enum import Enum

from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Date,
    DateTime,
    Boolean,
    Text,
    ForeignKey,
    Index,
    CheckConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


# =============================================================================
# ENUMS
# =============================================================================


class VATReportPeriod(str, Enum):
    """Meldezeitraum für USt-Voranmeldung."""
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


class BWAPeriod(str, Enum):
    """Auswertungszeitraum für BWA."""
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class SKRSchema(str, Enum):
    """Kontenrahmen-Schema."""
    SKR03 = "SKR03"
    SKR04 = "SKR04"


# =============================================================================
# UST-VORANMELDUNG MODEL
# =============================================================================


class UStVoranmeldung(Base):
    """
    USt-Voranmeldung - Umsatzsteuer-Voranmeldung.

    Aggregiert Vorsteuer aus Eingangsrechnungen und Umsatzsteuer
    aus Ausgangsrechnungen. ELSTER-kompatibel.

    Vorsteuer = Input VAT (Eingangsrechnungen / Einkauf)
    Umsatzsteuer = Output VAT (Ausgangsrechnungen / Verkauf)
    Zahllast = Umsatzsteuer - Vorsteuer (positiv = Nachzahlung ans FA)
    """
    __tablename__ = "ust_voranmeldungen"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Firma
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Zeitraum
    period_start = Column(Date, nullable=False, comment="Beginn des Meldezeitraums")
    period_end = Column(Date, nullable=False, comment="Ende des Meldezeitraums")
    period_type = Column(
        String(20),
        nullable=False,
        default=VATReportPeriod.MONTHLY.value,
        comment="monthly oder quarterly",
    )

    # Vorsteuer (Input VAT - aus Eingangsrechnungen)
    vorsteuer_summe = Column(
        Float, nullable=False, default=0.0,
        comment="Vorsteuer-Summe aus Eingangsrechnungen",
    )

    # Umsatzsteuer (Output VAT - aus Ausgangsrechnungen)
    umsatzsteuer_summe = Column(
        Float, nullable=False, default=0.0,
        comment="Umsatzsteuer-Summe aus Ausgangsrechnungen",
    )

    # Zahllast = Umsatzsteuer - Vorsteuer (positiv = Nachzahlung)
    zahllast = Column(
        Float, nullable=False, default=0.0,
        comment="Zahllast (USt - VSt), positiv = Zahlung ans Finanzamt",
    )

    # Steuerfreie Umsätze
    steuerfrei_inland = Column(
        Float, nullable=False, default=0.0,
        comment="Steuerfreie Umsätze Inland (z.B. Aerzte, Versicherungen)",
    )
    steuerfrei_export = Column(
        Float, nullable=False, default=0.0,
        comment="Steuerfreie Ausfuhrlieferungen (Export Drittland)",
    )
    innergemeinschaftliche_lieferungen = Column(
        Float, nullable=False, default=0.0,
        comment="Innergemeinschaftliche Lieferungen (EU)",
    )

    # Detail-Aufschluesselungen als JSON
    vorsteuer_details = Column(
        CrossDBJSON, nullable=True,
        comment="Vorsteuer je Steuersatz: {'19': ..., '7': ...}",
    )
    umsatzsteuer_details = Column(
        CrossDBJSON, nullable=True,
        comment="Umsatzsteuer je Steuersatz: {'19': ..., '7': ...}",
    )

    # Status: entwurf -> geprüft -> übermittelt
    status = Column(
        String(50), nullable=False, default="entwurf",
        comment="entwurf, geprüft, übermittelt",
    )

    # ELSTER-XML
    elster_xml = Column(Text, nullable=True, comment="Generiertes ELSTER-XML")

    # Notizen
    notes = Column(Text, nullable=True, comment="Interne Notizen")

    # Erstellt von
    created_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    company = relationship("Company", backref="ust_voranmeldungen")
    created_by = relationship("User", foreign_keys=[created_by_user_id])

    __table_args__ = (
        Index("ix_ust_va_company_period", "company_id", "period_start"),
        Index("ix_ust_va_status", "status"),
    )

    def to_dict(self) -> dict:
        """Konvertierung für API-Responses."""
        return {
            "id": str(self.id),
            "company_id": str(self.company_id),
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "period_type": self.period_type,
            "vorsteuer_summe": self.vorsteuer_summe,
            "umsatzsteuer_summe": self.umsatzsteuer_summe,
            "zahllast": self.zahllast,
            "steuerfrei_inland": self.steuerfrei_inland,
            "steuerfrei_export": self.steuerfrei_export,
            "innergemeinschaftliche_lieferungen": self.innergemeinschaftliche_lieferungen,
            "vorsteuer_details": self.vorsteuer_details,
            "umsatzsteuer_details": self.umsatzsteuer_details,
            "status": self.status,
            "elster_xml": self.elster_xml is not None,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# =============================================================================
# BWA REPORT MODEL
# =============================================================================


class BWAReport(Base):
    """
    BWA - Betriebswirtschaftliche Auswertung.

    Standard-BWA nach SKR03/SKR04 mit Vorjahresvergleich.
    Kontengruppen-basierte Aggregation:
    - Erloese: 8000-8999 (SKR03) / 4000-4999 (SKR04)
    - Materialaufwand: 3000-3999 (SKR03) / 5000-5999 (SKR04)
    - Personalaufwand: 4000-4999 (SKR03) / 6000-6999 (SKR04)
    - Sonstige Aufwendungen: 6000-6999 (SKR03) / 6000-6999 (SKR04)
    - Abschreibungen: 2000-2999 (SKR03) / 7000-7199 (SKR04)
    """
    __tablename__ = "bwa_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Firma
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Zeitraum
    period_start = Column(Date, nullable=False, comment="Beginn des Auswertungszeitraums")
    period_end = Column(Date, nullable=False, comment="Ende des Auswertungszeitraums")
    period_type = Column(
        String(20), nullable=False, default=BWAPeriod.MONTHLY.value,
        comment="monthly, quarterly, yearly",
    )

    # Kontenrahmen
    skr_schema = Column(
        String(10), nullable=False, default=SKRSchema.SKR03.value,
        comment="SKR03 oder SKR04",
    )

    # Detail-Positionen als JSON (Kontengruppe -> {label, betrag, konten: [...]})
    erloese = Column(CrossDBJSON, nullable=True, comment="Erloese nach Kontengruppe")
    materialaufwand = Column(CrossDBJSON, nullable=True, comment="Materialaufwand")
    personalaufwand = Column(CrossDBJSON, nullable=True, comment="Personalaufwand")
    sonstige_aufwendungen = Column(CrossDBJSON, nullable=True, comment="Sonstige Aufwendungen")
    abschreibungen = Column(CrossDBJSON, nullable=True, comment="Abschreibungen")

    # Ergebnisrechnung (aggregierte Float-Werte)
    betriebsergebnis = Column(Float, nullable=False, default=0.0, comment="EBIT")
    finanzergebnis = Column(Float, nullable=False, default=0.0, comment="Zinsen/Beteiligungen")
    ergebnis_vor_steuern = Column(Float, nullable=False, default=0.0, comment="EBT")
    steuern = Column(Float, nullable=False, default=0.0, comment="Ertragsteuern")
    jahresueberschuss = Column(Float, nullable=False, default=0.0, comment="Netto-Ergebnis")

    # Vorjahresvergleich (gleiche Struktur)
    vorjahresvergleich = Column(CrossDBJSON, nullable=True, comment="Vorjahresdaten")

    # Status: entwurf -> freigegeben -> archiviert
    status = Column(
        String(50), nullable=False, default="entwurf",
        comment="entwurf, freigegeben, archiviert",
    )

    # Erstellt von
    created_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    company = relationship("Company", backref="bwa_reports")
    created_by = relationship("User", foreign_keys=[created_by_user_id])

    __table_args__ = (
        Index("ix_bwa_company_period", "company_id", "period_start"),
        Index("ix_bwa_status", "status"),
    )

    def to_dict(self) -> dict:
        """Konvertierung für API-Responses."""
        return {
            "id": str(self.id),
            "company_id": str(self.company_id),
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "period_type": self.period_type,
            "skr_schema": self.skr_schema,
            "erloese": self.erloese,
            "materialaufwand": self.materialaufwand,
            "personalaufwand": self.personalaufwand,
            "sonstige_aufwendungen": self.sonstige_aufwendungen,
            "abschreibungen": self.abschreibungen,
            "betriebsergebnis": self.betriebsergebnis,
            "finanzergebnis": self.finanzergebnis,
            "ergebnis_vor_steuern": self.ergebnis_vor_steuern,
            "steuern": self.steuern,
            "jahresüberschuss": self.jahresueberschuss,
            "vorjahresvergleich": self.vorjahresvergleich,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# =============================================================================
# CASHFLOW FORECAST MODEL
# =============================================================================


class CashflowForecast(Base):
    """
    Cashflow-Prognose mit Szenarien.

    Intelligente Prognose basierend auf:
    - Offene Forderungen + historisches Zahlungsverhalten pro Kunde
    - Offene Verbindlichkeiten + eigene Zahlungsmuster
    - Saisonale Muster der letzten 12 Monate
    - Was-waere-wenn Szenarien (z.B. 'wenn_kunde_nicht_zahlt')

    Wird täglich automatisch regeneriert.
    """
    __tablename__ = "cashflow_forecasts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Firma
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Prognosedatum (für welchen Tag gilt die Prognose?)
    forecast_date = Column(
        Date, nullable=False,
        comment="Datum, für das die Prognose gilt",
    )
    forecast_generated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        comment="Zeitpunkt der Prognose-Erstellung",
    )

    # Horizont
    horizon_days = Column(Integer, nullable=False, default=90)

    # Prognosewerte
    predicted_balance = Column(
        Float, nullable=False, default=0.0,
        comment="Prognostizierter Kontostand",
    )
    confidence_lower = Column(Float, nullable=True, comment="Untere Konfidenzgrenze")
    confidence_upper = Column(Float, nullable=True, comment="Obere Konfidenzgrenze")

    # Einnahmen / Ausgaben
    einnahmen_prognose = Column(
        Float, nullable=False, default=0.0,
        comment="Prognostizierte Einnahmen",
    )
    ausgaben_prognose = Column(
        Float, nullable=False, default=0.0,
        comment="Prognostizierte Ausgaben",
    )

    # Offene Posten
    offene_forderungen = Column(
        Float, nullable=False, default=0.0,
        comment="Offene Forderungen (Debitoren)",
    )
    offene_verbindlichkeiten = Column(
        Float, nullable=False, default=0.0,
        comment="Offene Verbindlichkeiten (Kreditoren)",
    )

    # Saisonalitaet
    saisonaler_faktor = Column(
        Float, nullable=True,
        comment="Saisonaler Korrekturfaktor (1.0 = neutral)",
    )

    # Liquiditaetsengpass-Warnung
    warnung_liquiditaetsengpass = Column(
        Boolean, nullable=False, default=False,
        comment="True wenn Engpass prognostiziert",
    )
    engpass_datum = Column(
        Date, nullable=True,
        comment="Datum des prognostizierten Engpasses",
    )

    # Szenario
    scenario_type = Column(
        String(50), nullable=False, default="basis",
        comment="basis, optimistisch, pessimistisch, wenn_kunde_nicht_zahlt",
    )
    scenario_config = Column(
        CrossDBJSON, nullable=True,
        comment="Szenario-Parameter (z.B. {entity_id: ...})",
    )

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    company = relationship("Company", backref="cashflow_forecasts")

    __table_args__ = (
        Index("ix_cashflow_forecast_company_date", "company_id", "forecast_date"),
        Index("ix_cashflow_forecast_scenario", "company_id", "scenario_type"),
        Index("ix_cashflow_forecast_engpass", "warnung_liquiditaetsengpass"),
    )

    def to_dict(self) -> dict:
        """Konvertierung für API-Responses."""
        return {
            "id": str(self.id),
            "company_id": str(self.company_id),
            "forecast_date": self.forecast_date.isoformat() if self.forecast_date else None,
            "forecast_generated_at": (
                self.forecast_generated_at.isoformat()
                if self.forecast_generated_at else None
            ),
            "horizon_days": self.horizon_days,
            "predicted_balance": self.predicted_balance,
            "confidence_lower": self.confidence_lower,
            "confidence_upper": self.confidence_upper,
            "einnahmen_prognose": self.einnahmen_prognose,
            "ausgaben_prognose": self.ausgaben_prognose,
            "offene_forderungen": self.offene_forderungen,
            "offene_verbindlichkeiten": self.offene_verbindlichkeiten,
            "saisonaler_faktor": self.saisonaler_faktor,
            "warnung_liquiditaetsengpass": self.warnung_liquiditaetsengpass,
            "engpass_datum": (
                self.engpass_datum.isoformat() if self.engpass_datum else None
            ),
            "scenario_type": self.scenario_type,
            "scenario_config": self.scenario_config,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
