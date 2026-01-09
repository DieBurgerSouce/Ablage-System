"""Add calculated KPI fields to Privat module tables.

Revision ID: 081_add_privat_module_kpi_fields
Revises: 080_add_push_subscriptions
Create Date: 2026-01-08

Enterprise Feature: Automatische Berechnung von KPIs fuer:
- Immobilien (Mietrendite, ROI, Wertsteigerung)
- Fahrzeuge (TCO, Abschreibung, Verbrauch)
- Versicherungen (Deckungsanalyse, Kuendigungsfristen)
- Kredite (Tilgungsplan, Restlaufzeit, Zinsersparnis)
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers
revision = '081'
down_revision = '080'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ==================================================
    # PrivatProperty - Immobilien-KPIs
    # ==================================================

    # Bruttomietrendite in %
    op.add_column('privat_properties',
        sa.Column('calculated_yield', sa.Numeric(6, 2), nullable=True,
                  comment='Bruttomietrendite in Prozent'))

    # Nettomietrendite in %
    op.add_column('privat_properties',
        sa.Column('calculated_net_yield', sa.Numeric(6, 2), nullable=True,
                  comment='Nettomietrendite in Prozent'))

    # Wertzuwachs absolut
    op.add_column('privat_properties',
        sa.Column('value_appreciation', sa.Numeric(15, 2), nullable=True,
                  comment='Wertzuwachs in EUR'))

    # Wertzuwachs in %
    op.add_column('privat_properties',
        sa.Column('value_appreciation_rate', sa.Numeric(6, 2), nullable=True,
                  comment='Wertzuwachs in Prozent'))

    # Nebenkosten Year-to-Date
    op.add_column('privat_properties',
        sa.Column('total_costs_ytd', sa.Numeric(12, 2), nullable=True,
                  comment='Nebenkosten YTD in EUR'))

    # Gesamt-ROI in %
    op.add_column('privat_properties',
        sa.Column('calculated_roi', sa.Numeric(8, 2), nullable=True,
                  comment='Gesamt-ROI in Prozent'))

    # Jaehrlicher ROI in %
    op.add_column('privat_properties',
        sa.Column('annual_roi', sa.Numeric(6, 2), nullable=True,
                  comment='Jaehrlicher ROI in Prozent'))

    # Letzte KPI-Berechnung
    op.add_column('privat_properties',
        sa.Column('last_kpi_calculation', sa.DateTime(timezone=True), nullable=True,
                  comment='Zeitpunkt der letzten KPI-Berechnung'))

    # ==================================================
    # PrivatVehicle - Fahrzeug-KPIs
    # ==================================================

    # Geschaetzter Restwert
    op.add_column('privat_vehicles',
        sa.Column('current_estimated_value', sa.Numeric(12, 2), nullable=True,
                  comment='Geschaetzter aktueller Wert in EUR'))

    # Monatliche Abschreibung
    op.add_column('privat_vehicles',
        sa.Column('depreciation_monthly', sa.Numeric(10, 2), nullable=True,
                  comment='Monatliche Abschreibung in EUR'))

    # Total Cost of Ownership
    op.add_column('privat_vehicles',
        sa.Column('tco_total', sa.Numeric(12, 2), nullable=True,
                  comment='Total Cost of Ownership in EUR'))

    # Kosten pro Kilometer
    op.add_column('privat_vehicles',
        sa.Column('tco_per_km', sa.Numeric(6, 3), nullable=True,
                  comment='Kosten pro Kilometer in EUR'))

    # Naechster geplanter Service
    op.add_column('privat_vehicles',
        sa.Column('next_service_date', sa.Date(), nullable=True,
                  comment='Naechster geplanter Servicetermin'))

    # Service bei km-Stand
    op.add_column('privat_vehicles',
        sa.Column('next_service_km', sa.Integer(), nullable=True,
                  comment='Naechster Service bei km-Stand'))

    # Durchschnittsverbrauch
    op.add_column('privat_vehicles',
        sa.Column('average_fuel_consumption', sa.Numeric(5, 2), nullable=True,
                  comment='Durchschnittsverbrauch in l/100km'))

    # Letzte KPI-Berechnung
    op.add_column('privat_vehicles',
        sa.Column('last_kpi_calculation', sa.DateTime(timezone=True), nullable=True,
                  comment='Zeitpunkt der letzten KPI-Berechnung'))

    # ==================================================
    # PrivatInsurance - Versicherungs-KPIs
    # ==================================================

    # Deckungsluecken-Analyse (JSONB)
    op.add_column('privat_insurances',
        sa.Column('coverage_gap_analysis', JSONB, nullable=True,
                  comment='Deckungsluecken-Analyse als JSON'))

    # Berechnete Kuendigungsfrist
    op.add_column('privat_insurances',
        sa.Column('cancellation_deadline', sa.Date(), nullable=True,
                  comment='Berechnete Kuendigungsfrist'))

    # Jaehrliche Gesamtpraemie
    op.add_column('privat_insurances',
        sa.Column('annual_premium_total', sa.Numeric(10, 2), nullable=True,
                  comment='Jaehrliche Gesamtpraemie in EUR'))

    # Deckungsadaequanz-Score
    op.add_column('privat_insurances',
        sa.Column('coverage_adequacy_score', sa.Numeric(5, 2), nullable=True,
                  comment='Deckungsadaequanz-Score 0-100'))

    # Letzte KPI-Berechnung
    op.add_column('privat_insurances',
        sa.Column('last_kpi_calculation', sa.DateTime(timezone=True), nullable=True,
                  comment='Zeitpunkt der letzten KPI-Berechnung'))

    # ==================================================
    # PrivatLoan - Kredit-KPIs
    # ==================================================

    # Tilgungsplan (JSONB)
    op.add_column('privat_loans',
        sa.Column('amortization_schedule', JSONB, nullable=True,
                  comment='Tilgungsplan als JSON'))

    # Voraussichtliches Rueckzahlungsdatum
    op.add_column('privat_loans',
        sa.Column('projected_payoff_date', sa.Date(), nullable=True,
                  comment='Voraussichtliches Rueckzahlungsdatum'))

    # Erwartete Gesamtzinsen
    op.add_column('privat_loans',
        sa.Column('total_interest_projected', sa.Numeric(15, 2), nullable=True,
                  comment='Erwartete Gesamtzinsen in EUR'))

    # Zinsersparnis bei Sondertilgung
    op.add_column('privat_loans',
        sa.Column('interest_saved_with_extra', sa.Numeric(12, 2), nullable=True,
                  comment='Moegliche Zinsersparnis bei Sondertilgung in EUR'))

    # Effektiver Jahreszins
    op.add_column('privat_loans',
        sa.Column('effective_annual_rate', sa.Numeric(5, 3), nullable=True,
                  comment='Effektiver Jahreszins in Prozent'))

    # Verbleibende Laufzeit in Monaten
    op.add_column('privat_loans',
        sa.Column('remaining_term_months', sa.Integer(), nullable=True,
                  comment='Verbleibende Laufzeit in Monaten'))

    # Letzte KPI-Berechnung
    op.add_column('privat_loans',
        sa.Column('last_kpi_calculation', sa.DateTime(timezone=True), nullable=True,
                  comment='Zeitpunkt der letzten KPI-Berechnung'))

    # ==================================================
    # Indexes fuer KPI-Abfragen
    # ==================================================

    # Property KPI Indexes
    op.create_index(
        'ix_privat_properties_calculated_yield',
        'privat_properties', ['calculated_yield'],
        postgresql_where=sa.text('calculated_yield IS NOT NULL')
    )
    op.create_index(
        'ix_privat_properties_last_kpi_calculation',
        'privat_properties', ['last_kpi_calculation']
    )

    # Vehicle KPI Indexes
    op.create_index(
        'ix_privat_vehicles_next_service_date',
        'privat_vehicles', ['next_service_date'],
        postgresql_where=sa.text('next_service_date IS NOT NULL')
    )
    op.create_index(
        'ix_privat_vehicles_last_kpi_calculation',
        'privat_vehicles', ['last_kpi_calculation']
    )

    # Insurance KPI Indexes
    op.create_index(
        'ix_privat_insurances_cancellation_deadline',
        'privat_insurances', ['cancellation_deadline'],
        postgresql_where=sa.text('cancellation_deadline IS NOT NULL')
    )
    op.create_index(
        'ix_privat_insurances_last_kpi_calculation',
        'privat_insurances', ['last_kpi_calculation']
    )

    # Loan KPI Indexes
    op.create_index(
        'ix_privat_loans_projected_payoff_date',
        'privat_loans', ['projected_payoff_date'],
        postgresql_where=sa.text('projected_payoff_date IS NOT NULL')
    )
    op.create_index(
        'ix_privat_loans_last_kpi_calculation',
        'privat_loans', ['last_kpi_calculation']
    )


def downgrade() -> None:
    # ==================================================
    # Drop Indexes
    # ==================================================

    op.drop_index('ix_privat_loans_last_kpi_calculation', table_name='privat_loans')
    op.drop_index('ix_privat_loans_projected_payoff_date', table_name='privat_loans')
    op.drop_index('ix_privat_insurances_last_kpi_calculation', table_name='privat_insurances')
    op.drop_index('ix_privat_insurances_cancellation_deadline', table_name='privat_insurances')
    op.drop_index('ix_privat_vehicles_last_kpi_calculation', table_name='privat_vehicles')
    op.drop_index('ix_privat_vehicles_next_service_date', table_name='privat_vehicles')
    op.drop_index('ix_privat_properties_last_kpi_calculation', table_name='privat_properties')
    op.drop_index('ix_privat_properties_calculated_yield', table_name='privat_properties')

    # ==================================================
    # Drop PrivatLoan Columns
    # ==================================================

    op.drop_column('privat_loans', 'last_kpi_calculation')
    op.drop_column('privat_loans', 'remaining_term_months')
    op.drop_column('privat_loans', 'effective_annual_rate')
    op.drop_column('privat_loans', 'interest_saved_with_extra')
    op.drop_column('privat_loans', 'total_interest_projected')
    op.drop_column('privat_loans', 'projected_payoff_date')
    op.drop_column('privat_loans', 'amortization_schedule')

    # ==================================================
    # Drop PrivatInsurance Columns
    # ==================================================

    op.drop_column('privat_insurances', 'last_kpi_calculation')
    op.drop_column('privat_insurances', 'coverage_adequacy_score')
    op.drop_column('privat_insurances', 'annual_premium_total')
    op.drop_column('privat_insurances', 'cancellation_deadline')
    op.drop_column('privat_insurances', 'coverage_gap_analysis')

    # ==================================================
    # Drop PrivatVehicle Columns
    # ==================================================

    op.drop_column('privat_vehicles', 'last_kpi_calculation')
    op.drop_column('privat_vehicles', 'average_fuel_consumption')
    op.drop_column('privat_vehicles', 'next_service_km')
    op.drop_column('privat_vehicles', 'next_service_date')
    op.drop_column('privat_vehicles', 'tco_per_km')
    op.drop_column('privat_vehicles', 'tco_total')
    op.drop_column('privat_vehicles', 'depreciation_monthly')
    op.drop_column('privat_vehicles', 'current_estimated_value')

    # ==================================================
    # Drop PrivatProperty Columns
    # ==================================================

    op.drop_column('privat_properties', 'last_kpi_calculation')
    op.drop_column('privat_properties', 'annual_roi')
    op.drop_column('privat_properties', 'calculated_roi')
    op.drop_column('privat_properties', 'total_costs_ytd')
    op.drop_column('privat_properties', 'value_appreciation_rate')
    op.drop_column('privat_properties', 'value_appreciation')
    op.drop_column('privat_properties', 'calculated_net_yield')
    op.drop_column('privat_properties', 'calculated_yield')
