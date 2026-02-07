# -*- coding: utf-8 -*-
"""
Fixtures fuer ESG Services Unit Tests.

Stellt bereit:
- Mock Company, User
- AsyncSession Mock
- Sample ESG Data Generators (Emissions, Ratings, Certifications)

Feinpoliert und durchdacht - ESG Test Fixtures.
"""

from datetime import datetime, timezone, timedelta, date
from decimal import Decimal
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import UUID, uuid4

import pytest


# ========================= ID Fixtures =========================


@pytest.fixture
def company_id() -> UUID:
    """Fixed company ID for tests."""
    return UUID("12345678-1234-1234-1234-123456789abc")


@pytest.fixture
def user_id() -> UUID:
    """Fixed user ID for tests."""
    return UUID("11111111-2222-3333-4444-555555555555")


@pytest.fixture
def entity_id() -> UUID:
    """Fixed entity (supplier) ID for tests."""
    return UUID("abcdef12-3456-7890-abcd-ef1234567890")


# ========================= AsyncSession Mock =========================


@pytest.fixture
def mock_db() -> AsyncMock:
    """
    Provide AsyncSession mock.

    Can be configured per test for specific query results.
    """
    db = AsyncMock()
    db.add = MagicMock()
    db.delete = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    return db


def create_mock_result(scalar_value: Any = None, scalars_list: Optional[List] = None):
    """
    Helper to create mock result for db.execute().

    Args:
        scalar_value: Value for result.scalar_one_or_none()
        scalars_list: List for result.scalars().all()
    """
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=scalar_value)
    result.scalar = MagicMock(return_value=scalar_value)

    if scalars_list is not None:
        scalars_mock = MagicMock()
        scalars_mock.all = MagicMock(return_value=scalars_list)
        result.scalars = MagicMock(return_value=scalars_mock)
    else:
        result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))

    return result


# ========================= Carbon Emission Fixtures =========================


@pytest.fixture
def sample_emission(company_id: UUID) -> MagicMock:
    """Provide sample carbon emission record."""
    emission = MagicMock()
    emission.id = uuid4()
    emission.company_id = company_id
    emission.period_start = date.today() - timedelta(days=30)
    emission.period_end = date.today()
    emission.source_category = "electricity"
    emission.consumption_value = 10000.0
    emission.consumption_unit = "kWh"
    emission.emission_factor = 0.42
    emission.emission_factor_unit = "kg CO2/kWh"
    emission.emission_factor_source = "UBA 2024"
    emission.co2_equivalent_kg = 4200.0
    emission.scope = "scope_2"
    emission.data_quality = "medium"
    emission.calculation_method = "GHG Protocol"
    emission.source_description = "Stromverbrauch Buero"
    emission.verified = False
    emission.verified_at = None
    emission.verified_by_id = None
    emission.document_id = None
    emission.notes = None
    emission.created_at = datetime.now(timezone.utc)
    emission.updated_at = datetime.now(timezone.utc)
    return emission


@pytest.fixture
def sample_emissions(company_id: UUID) -> List[MagicMock]:
    """Generate list of sample emissions."""
    categories = [
        ("electricity", "kWh", 10000, 0.42, 4200, "scope_2"),
        ("natural_gas", "m3", 5000, 2.0, 10000, "scope_1"),
        ("diesel", "L", 2000, 2.68, 5360, "scope_1"),
        ("business_travel_air", "km", 10000, 0.255, 2550, "scope_3"),
        ("commuting", "km", 50000, 0.12, 6000, "scope_3"),
    ]

    emissions = []
    for cat, unit, value, factor, co2, scope in categories:
        emission = MagicMock()
        emission.id = uuid4()
        emission.company_id = company_id
        emission.period_start = date.today() - timedelta(days=30)
        emission.period_end = date.today()
        emission.source_category = cat
        emission.consumption_value = float(value)
        emission.consumption_unit = unit
        emission.emission_factor = factor
        emission.co2_equivalent_kg = float(co2)
        emission.scope = scope
        emission.data_quality = "medium"
        emission.verified = False
        emission.created_at = datetime.now(timezone.utc)
        emissions.append(emission)

    return emissions


# ========================= Supplier Rating Fixtures =========================


@pytest.fixture
def sample_rating(company_id: UUID, entity_id: UUID, user_id: UUID) -> MagicMock:
    """Provide sample supplier rating."""
    rating = MagicMock()
    rating.id = uuid4()
    rating.company_id = company_id
    rating.entity_id = entity_id
    rating.environmental_score = 75.0
    rating.social_score = 80.0
    rating.governance_score = 85.0
    rating.overall_score = 80.0
    rating.risk_level = "low"
    rating.environmental_details = {
        "energy_efficiency": 80,
        "waste_management": 70,
        "emissions_reduction": 75,
    }
    rating.social_details = {
        "labor_practices": 85,
        "health_safety": 80,
        "diversity_inclusion": 75,
    }
    rating.governance_details = {
        "ethics_compliance": 90,
        "transparency": 85,
        "risk_management": 80,
    }
    rating.certifications = ["ISO 14001", "ISO 45001"]
    rating.improvement_areas = ["waste_management"]
    rating.action_plan = "Implement recycling program"
    rating.assessment_method = "self_assessment"
    rating.assessed_by_id = user_id
    rating.assessment_date = date.today()
    rating.valid_until = date.today() + timedelta(days=365)
    rating.notes = None
    rating.created_at = datetime.now(timezone.utc)
    rating.updated_at = datetime.now(timezone.utc)
    return rating


@pytest.fixture
def sample_ratings(company_id: UUID) -> List[MagicMock]:
    """Generate list of sample supplier ratings."""
    risk_levels = ["low", "medium", "high", "critical"]
    ratings = []

    for i, risk in enumerate(risk_levels):
        rating = MagicMock()
        rating.id = uuid4()
        rating.company_id = company_id
        rating.entity_id = uuid4()
        rating.entity_name = f"Lieferant {i+1} GmbH"
        rating.environmental_score = 90 - (i * 15)
        rating.social_score = 85 - (i * 15)
        rating.governance_score = 80 - (i * 15)
        rating.overall_score = (rating.environmental_score + rating.social_score + rating.governance_score) / 3
        rating.risk_level = risk
        rating.assessment_date = date.today() - timedelta(days=i * 30)
        rating.created_at = datetime.now(timezone.utc)
        ratings.append(rating)

    return ratings


# ========================= Certification Fixtures =========================


@pytest.fixture
def sample_certification(company_id: UUID) -> MagicMock:
    """Provide sample certification."""
    cert = MagicMock()
    cert.id = uuid4()
    cert.company_id = company_id
    cert.certification_type = "environmental"
    cert.certification_name = "ISO 14001:2015"
    cert.certification_body = "TUeV Rheinland"
    cert.certificate_number = "ENV-2024-12345"
    cert.issue_date = date.today() - timedelta(days=365)
    cert.expiry_date = date.today() + timedelta(days=730)
    cert.status = "active"
    cert.category = "environmental"
    cert.scope_description = "Umweltmanagementsystem fuer alle Standorte"
    cert.applicable_sites = ["Hauptsitz Berlin", "Niederlassung Muenchen"]
    cert.document_id = uuid4()
    cert.next_audit_date = date.today() + timedelta(days=180)
    cert.reminder_days_before = 90
    cert.notes = None
    cert.created_at = datetime.now(timezone.utc)
    cert.updated_at = datetime.now(timezone.utc)
    return cert


@pytest.fixture
def sample_certifications(company_id: UUID) -> List[MagicMock]:
    """Generate list of sample certifications."""
    certs_data = [
        ("ISO 14001:2015", "environmental", "active", 730),
        ("ISO 45001:2018", "social", "active", 365),
        ("ISO 9001:2015", "governance", "active", 180),
        ("EcoVadis Gold", "environmental", "active", 90),
        ("ISO 27001:2022", "governance", "expiring", 30),
    ]

    certifications = []
    for name, category, status, days_until_expiry in certs_data:
        cert = MagicMock()
        cert.id = uuid4()
        cert.company_id = company_id
        cert.certification_name = name
        cert.certification_type = category
        cert.category = category
        cert.status = status
        cert.issue_date = date.today() - timedelta(days=365)
        cert.expiry_date = date.today() + timedelta(days=days_until_expiry)
        cert.certification_body = "TUeV Rheinland"
        cert.next_audit_date = date.today() + timedelta(days=days_until_expiry - 30)
        cert.created_at = datetime.now(timezone.utc)
        certifications.append(cert)

    return certifications


# ========================= ESG Report Fixtures =========================


@pytest.fixture
def sample_report(company_id: UUID, user_id: UUID) -> MagicMock:
    """Provide sample ESG report."""
    report = MagicMock()
    report.id = uuid4()
    report.company_id = company_id
    report.report_type = "annual_sustainability"
    report.title = "Nachhaltigkeitsbericht 2025"
    report.period_start = date(2025, 1, 1)
    report.period_end = date(2025, 12, 31)
    report.status = "draft"
    report.reporting_standard = "GRI"
    report.content = {}
    report.generated_at = datetime.now(timezone.utc)
    report.created_by_id = user_id
    report.approved_by_id = None
    report.approved_at = None
    report.published_at = None
    report.document_id = None
    report.notes = None
    report.created_at = datetime.now(timezone.utc)
    report.updated_at = datetime.now(timezone.utc)
    return report


# ========================= ESG Goal Fixtures =========================


@pytest.fixture
def sample_goal(company_id: UUID) -> MagicMock:
    """Provide sample ESG goal."""
    goal = MagicMock()
    goal.id = uuid4()
    goal.company_id = company_id
    goal.title = "CO2-Reduktion um 30%"
    goal.description = "Reduktion der CO2-Emissionen um 30% bis 2030"
    goal.category = "environmental"
    goal.metric_name = "co2_emissions"
    goal.metric_unit = "t CO2e"
    goal.baseline_value = 10000.0
    goal.baseline_year = 2020
    goal.target_value = 7000.0
    goal.target_year = 2030
    goal.current_value = 8500.0
    goal.progress_percentage = 50.0
    goal.on_track = True
    goal.sdg_goals = [7, 12, 13]
    goal.status = "active"
    goal.notes = None
    goal.created_at = datetime.now(timezone.utc)
    goal.updated_at = datetime.now(timezone.utc)
    return goal


@pytest.fixture
def sample_goals(company_id: UUID) -> List[MagicMock]:
    """Generate list of sample ESG goals."""
    goals_data = [
        ("CO2-Reduktion", "environmental", 10000, 7000, 8500, 50, True, [13]),
        ("Erneuerbare Energie", "environmental", 20, 80, 55, 58, True, [7]),
        ("Diversitaet erhoehen", "social", 25, 40, 35, 66, True, [5, 10]),
        ("Zero Waste", "environmental", 1000, 0, 400, 60, False, [12]),
    ]

    goals = []
    for title, cat, base, target, current, progress, on_track, sdgs in goals_data:
        goal = MagicMock()
        goal.id = uuid4()
        goal.company_id = company_id
        goal.title = title
        goal.category = cat
        goal.baseline_value = float(base)
        goal.target_value = float(target)
        goal.current_value = float(current)
        goal.progress_percentage = float(progress)
        goal.on_track = on_track
        goal.sdg_goals = sdgs
        goal.status = "active"
        goal.created_at = datetime.now(timezone.utc)
        goals.append(goal)

    return goals


# ========================= Helper Functions =========================


def generate_emissions_by_scope(
    company_id: UUID,
    scope: str,
    count: int = 3
) -> List[MagicMock]:
    """Generate emissions for a specific scope."""
    emissions = []
    for i in range(count):
        emission = MagicMock()
        emission.id = uuid4()
        emission.company_id = company_id
        emission.scope = scope
        emission.co2_equivalent_kg = 1000.0 * (i + 1)
        emission.period_start = date.today() - timedelta(days=30 * (i + 1))
        emission.period_end = date.today() - timedelta(days=30 * i)
        emission.source_category = f"category_{i}"
        emission.verified = i % 2 == 0
        emissions.append(emission)
    return emissions
