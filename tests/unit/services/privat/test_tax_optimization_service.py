# -*- coding: utf-8 -*-
"""
Unit-Tests fuer TaxOptimizationService

Testet:
- Service-Initialisierung
- Dataclass-Strukturen
- Enum-Werte
- Steuerkonstanten
- Berechnungsmethoden

SECURITY: Niemals echte PII in Tests verwenden!
"""

import pytest
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Dict, Any, List
from uuid import uuid4

from app.services.privat.tax_optimization_service import (
    TaxOptimizationService,
    get_tax_optimization_service,
    # Enums
    TaxCategory,
    TaxRating,
    TaxDeadlineType,
    ElsterAnlage,
    ElsterFieldMapping,
    # Dataclasses
    TaxDeductionItem,
    TaxDeductionSummary,
    TaxOptimizationResult,
    TaxProjection,
    TaxSavingsEstimate,
    TaxDeadline,
    # Constants
    GRUNDFREIBETRAG_BY_YEAR,
    WERBUNGSKOSTEN_PAUSCHALE,
    HAUSHALTSNAHE_MAX_ABZUG,
    HANDWERKER_MAX_ABZUG,
    PENDLER_PAUSCHALE_PRO_KM_BIS_20,
    PENDLER_PAUSCHALE_PRO_KM_AB_21,
    HOMEOFFICE_TAGESSATZ,
    HOMEOFFICE_MAX_TAGE,
    SPARERFREIBETRAG_SINGLE,
    SPARERFREIBETRAG_VERHEIRATET,
    VORAUSZAHLUNGSTERMINE,
)


class TestTaxOptimizationServiceInitialization:
    """Tests fuer TaxOptimizationService Initialisierung."""

    def test_service_initialization(self) -> None:
        """Testet Service-Initialisierung."""
        service = get_tax_optimization_service()
        assert service is not None

    def test_singleton_pattern(self) -> None:
        """Testet dass Service ein Singleton ist."""
        service1 = get_tax_optimization_service()
        service2 = get_tax_optimization_service()
        assert service1 is service2


class TestTaxCategoryEnum:
    """Tests fuer TaxCategory Enum."""

    def test_tax_category_values(self) -> None:
        """Testet dass alle TaxCategory Werte korrekt sind."""
        assert TaxCategory.WERBUNGSKOSTEN.value == "werbungskosten"
        assert TaxCategory.SONDERAUSGABEN.value == "sonderausgaben"
        assert TaxCategory.AUSSERGEWOEHNLICHE_BELASTUNGEN.value == "aussergewoehnliche_belastungen"
        assert TaxCategory.HAUSHALTSNAHE_DIENSTLEISTUNGEN.value == "haushaltsnahe_dienstleistungen"
        assert TaxCategory.HANDWERKERLEISTUNGEN.value == "handwerkerleistungen"
        assert TaxCategory.DOPPELTE_HAUSHALTSFUEHRUNG.value == "doppelte_haushaltsfuehrung"
        assert TaxCategory.HOMEOFFICE.value == "homeoffice"
        assert TaxCategory.KINDERBETREUUNG.value == "kinderbetreuung"
        assert TaxCategory.SPENDEN.value == "spenden"
        assert TaxCategory.KIRCHENSTEUER.value == "kirchensteuer"

    def test_tax_category_count(self) -> None:
        """Testet dass genau 10 Kategorien existieren."""
        assert len(TaxCategory) == 10


class TestTaxRatingEnum:
    """Tests fuer TaxRating Enum."""

    def test_tax_rating_values(self) -> None:
        """Testet dass alle TaxRating Werte korrekt sind."""
        assert TaxRating.OPTIMAL.value == "optimal"
        assert TaxRating.GUT.value == "gut"
        assert TaxRating.VERBESSERBAR.value == "verbesserbar"
        assert TaxRating.OPTIMIERUNGSBEDARF.value == "optimierungsbedarf"

    def test_tax_rating_count(self) -> None:
        """Testet dass genau 4 Rating-Stufen existieren."""
        assert len(TaxRating) == 4


class TestElsterAnlageEnum:
    """Tests fuer ElsterAnlage Enum."""

    def test_elster_anlage_values(self) -> None:
        """Testet dass alle ELSTER Anlage-Werte korrekt sind."""
        assert ElsterAnlage.MANTELBOGEN.value == "mantelbogen"
        assert ElsterAnlage.ANLAGE_N.value == "anlage_n"
        assert ElsterAnlage.ANLAGE_V.value == "anlage_v"
        assert ElsterAnlage.ANLAGE_EUER.value == "anlage_euer"
        assert ElsterAnlage.ANLAGE_KAP.value == "anlage_kap"
        assert ElsterAnlage.ANLAGE_R.value == "anlage_r"
        assert ElsterAnlage.ANLAGE_SO.value == "anlage_so"
        assert ElsterAnlage.ANLAGE_VORSORGE.value == "anlage_vorsorge"
        assert ElsterAnlage.ANLAGE_HAUSHALTSNAHE.value == "anlage_haushaltsnahe"
        assert ElsterAnlage.ANLAGE_KIND.value == "anlage_kind"
        assert ElsterAnlage.ANLAGE_UNTERHALT.value == "anlage_unterhalt"
        assert ElsterAnlage.ANLAGE_AV.value == "anlage_av"

    def test_elster_anlage_count(self) -> None:
        """Testet dass alle Anlagen vorhanden sind."""
        assert len(ElsterAnlage) == 12


class TestTaxConstants:
    """Tests fuer Steuerkonstanten."""

    def test_grundfreibetrag_2024(self) -> None:
        """Testet Grundfreibetrag 2024."""
        assert GRUNDFREIBETRAG_BY_YEAR[2024] == Decimal("11604")

    def test_grundfreibetrag_2025(self) -> None:
        """Testet Grundfreibetrag 2025."""
        assert GRUNDFREIBETRAG_BY_YEAR[2025] == Decimal("12084")

    def test_grundfreibetrag_2026(self) -> None:
        """Testet Grundfreibetrag 2026."""
        assert GRUNDFREIBETRAG_BY_YEAR[2026] == Decimal("12096")

    def test_werbungskosten_pauschbetrag(self) -> None:
        """Testet Werbungskosten-Pauschbetrag."""
        assert WERBUNGSKOSTEN_PAUSCHALE == Decimal("1230")

    def test_sparerpauschbetrag_values(self) -> None:
        """Testet Sparerpauschbetraege."""
        assert SPARERFREIBETRAG_SINGLE == Decimal("1000")
        assert SPARERFREIBETRAG_VERHEIRATET == Decimal("2000")

    def test_haushaltsnahe_max(self) -> None:
        """Testet Maximum fuer haushaltsnahe Dienstleistungen."""
        assert HAUSHALTSNAHE_MAX_ABZUG == Decimal("4000")

    def test_handwerker_max(self) -> None:
        """Testet Maximum fuer Handwerkerleistungen."""
        assert HANDWERKER_MAX_ABZUG == Decimal("1200")

    def test_entfernungspauschale(self) -> None:
        """Testet Entfernungspauschalen."""
        assert PENDLER_PAUSCHALE_PRO_KM_BIS_20 == Decimal("0.30")
        assert PENDLER_PAUSCHALE_PRO_KM_AB_21 == Decimal("0.38")

    def test_homeoffice_pauschale(self) -> None:
        """Testet Home-Office Pauschale."""
        assert HOMEOFFICE_TAGESSATZ == Decimal("6")
        assert HOMEOFFICE_MAX_TAGE == 210

    def test_vorauszahlungstermine(self) -> None:
        """Testet Vorauszahlungstermine."""
        assert len(VORAUSZAHLUNGSTERMINE) == 4
        # Erste Vorauszahlung: 10. Maerz
        assert VORAUSZAHLUNGSTERMINE[0] == (3, 10)
        # Letzte Vorauszahlung: 10. Dezember
        assert VORAUSZAHLUNGSTERMINE[3] == (12, 10)


class TestTaxDeadlineTypes:
    """Tests fuer Steuerfristen-Typen."""

    def test_deadline_type_values(self) -> None:
        """Testet dass alle TaxDeadlineType Werte korrekt sind."""
        assert TaxDeadlineType.EINKOMMENSTEUER.value == "einkommensteuer"
        assert TaxDeadlineType.GEWERBESTEUER.value == "gewerbesteuer"
        assert TaxDeadlineType.UMSATZSTEUER_VORANMELDUNG.value == "umsatzsteuer_voranmeldung"
        assert TaxDeadlineType.GRUNDSTEUER.value == "grundsteuer"

    def test_deadline_type_count(self) -> None:
        """Testet dass alle Deadline-Typen vorhanden sind."""
        assert len(TaxDeadlineType) >= 4


class TestTaxDeductionItemDataClass:
    """Tests fuer TaxDeductionItem Datenstruktur."""

    def test_tax_deduction_item_creation(self) -> None:
        """Testet TaxDeductionItem Erstellung."""
        item = TaxDeductionItem(
            category=TaxCategory.WERBUNGSKOSTEN,
            description="Pendlerpauschale",
            gross_amount=Decimal("3000"),
            deductible_amount=Decimal("2500"),
            document_id=uuid4(),
            confidence=Decimal("0.95"),
            is_verified=True,
            notes="Berechnung korrekt",
        )

        assert item.category == TaxCategory.WERBUNGSKOSTEN
        assert item.description == "Pendlerpauschale"
        assert item.gross_amount == Decimal("3000")
        assert item.deductible_amount == Decimal("2500")
        assert item.confidence == Decimal("0.95")
        assert item.is_verified is True

    def test_tax_deduction_item_optional_fields(self) -> None:
        """Testet TaxDeductionItem mit optionalen Feldern."""
        item = TaxDeductionItem(
            category=TaxCategory.SONDERAUSGABEN,
            description="Kirchensteuer",
            gross_amount=Decimal("500"),
            deductible_amount=Decimal("500"),
            document_id=None,
            confidence=Decimal("1.0"),
            is_verified=True,
            notes=None,
        )

        assert item.document_id is None
        assert item.notes is None


class TestTaxDeductionSummaryDataClass:
    """Tests fuer TaxDeductionSummary Datenstruktur."""

    def test_tax_deduction_summary_creation(self) -> None:
        """Testet TaxDeductionSummary Erstellung."""
        item = TaxDeductionItem(
            category=TaxCategory.WERBUNGSKOSTEN,
            description="Test",
            gross_amount=Decimal("1500"),
            deductible_amount=Decimal("1500"),
            document_id=None,
            confidence=1.0,
            is_verified=True,
            notes=None,
        )

        summary = TaxDeductionSummary(
            category=TaxCategory.WERBUNGSKOSTEN,
            category_name="Werbungskosten",
            total_gross=Decimal("1500"),
            total_deductible=Decimal("1500"),
            max_deductible=None,
            utilization_percent=None,
            items=[item],
            recommendations=["Entfernungspauschale beachten"],
        )

        assert summary.category == TaxCategory.WERBUNGSKOSTEN
        assert summary.category_name == "Werbungskosten"
        assert len(summary.items) == 1
        assert len(summary.recommendations) == 1


class TestTaxProjectionDataClass:
    """Tests fuer TaxProjection Datenstruktur."""

    def test_tax_projection_dataclass_exists(self) -> None:
        """Testet dass TaxProjection existiert und instanziierbar ist."""
        # TaxProjection erfordert viele Felder - testen wir nur Existenz
        assert TaxProjection is not None


class TestTaxSavingsEstimateDataClass:
    """Tests fuer TaxSavingsEstimate Datenstruktur."""

    def test_tax_savings_estimate_creation(self) -> None:
        """Testet TaxSavingsEstimate Erstellung."""
        estimate = TaxSavingsEstimate(
            estimated_gross_income=Decimal("60000"),
            total_deductions=Decimal("5000"),
            taxable_income=Decimal("55000"),
            estimated_tax_without_deductions=Decimal("15000"),
            estimated_tax_with_deductions=Decimal("12000"),
            estimated_savings=Decimal("3000"),
            effective_tax_rate=Decimal("20"),
            marginal_tax_rate=Decimal("35"),
        )

        assert estimate.estimated_gross_income == Decimal("60000")
        assert estimate.estimated_savings == Decimal("3000")
        assert estimate.marginal_tax_rate == Decimal("35")


class TestTaxDeadlineDataClass:
    """Tests fuer TaxDeadline Datenstruktur."""

    def test_tax_deadline_creation(self) -> None:
        """Testet TaxDeadline Erstellung."""
        deadline = TaxDeadline(
            deadline_type=TaxDeadlineType.EINKOMMENSTEUER,
            title="Einkommensteuererklärung 2024",
            due_date=date(2025, 7, 31),
            description="Abgabefrist ohne Steuerberater",
            is_recurring=True,
            recurrence_pattern="yearly",
            days_until_due=180,
            is_overdue=False,
        )

        assert deadline.deadline_type == TaxDeadlineType.EINKOMMENSTEUER
        assert deadline.title == "Einkommensteuererklärung 2024"
        assert deadline.days_until_due == 180
        assert deadline.is_overdue is False
        assert deadline.is_recurring is True


class TestTaxOptimizationResultDataClass:
    """Tests fuer TaxOptimizationResult Datenstruktur."""

    def test_tax_optimization_result_creation(self) -> None:
        """Testet TaxOptimizationResult Erstellung."""
        summary = TaxDeductionSummary(
            category=TaxCategory.WERBUNGSKOSTEN,
            category_name="Werbungskosten",
            total_gross=Decimal("2000"),
            total_deductible=Decimal("2000"),
            max_deductible=None,
            utilization_percent=None,
            items=[],
            recommendations=[],
        )

        result = TaxOptimizationResult(
            space_id=uuid4(),
            tax_year=2024,
            total_deductible=Decimal("8500"),
            estimated_tax_savings=Decimal("2890"),
            optimization_rating=TaxRating.GUT,
            deduction_summaries=[summary],
            upcoming_deadlines=[],
            overdue_deadlines=[],
            optimization_suggestions=[
                "Haushaltsnahe Dienstleistungen nutzen",
            ],
            missing_deductions=[
                "Keine Handwerkerleistungen erfasst",
            ],
            datev_export_ready=True,
        )

        assert result.tax_year == 2024
        assert result.optimization_rating == TaxRating.GUT
        assert result.total_deductible == Decimal("8500")
        assert result.estimated_tax_savings == Decimal("2890")
        assert len(result.deduction_summaries) == 1
        assert len(result.optimization_suggestions) == 1


class TestTaxCalculations:
    """Tests fuer Steuerberechnungen."""

    @pytest.fixture
    def service(self) -> TaxOptimizationService:
        """Fixture fuer TaxOptimizationService."""
        return get_tax_optimization_service()

    def test_calculate_income_tax_zero_income(self, service: TaxOptimizationService) -> None:
        """Testet Einkommensteuer bei Null-Einkommen."""
        tax = service._calculate_single_tax(Decimal("0"))
        assert tax == Decimal("0")

    def test_calculate_income_tax_negative_income(self, service: TaxOptimizationService) -> None:
        """Testet Einkommensteuer bei negativem Einkommen (Verlust)."""
        tax = service._calculate_single_tax(Decimal("-5000"))
        assert tax == Decimal("0")

    def test_calculate_income_tax_zone_2(self, service: TaxOptimizationService) -> None:
        """Testet Einkommensteuer Zone 2 (Progression)."""
        # Einkommen knapp ueber Grundfreibetrag
        tax = service._calculate_single_tax(Decimal("15000"))
        assert tax > Decimal("0")
        # Sollte unter 1500 EUR liegen bei diesem Einkommen
        assert tax < Decimal("1500")

    def test_calculate_income_tax_zone_3(self, service: TaxOptimizationService) -> None:
        """Testet Einkommensteuer Zone 3."""
        tax = service._calculate_single_tax(Decimal("25000"))
        assert tax > Decimal("0")

    def test_calculate_income_tax_zone_4(self, service: TaxOptimizationService) -> None:
        """Testet Einkommensteuer Zone 4 (42%)."""
        tax = service._calculate_single_tax(Decimal("80000"))
        assert tax > Decimal("15000")

    def test_calculate_income_tax_zone_5(self, service: TaxOptimizationService) -> None:
        """Testet Einkommensteuer Zone 5 (45% - Reichensteuer)."""
        tax = service._calculate_single_tax(Decimal("300000"))
        assert tax > Decimal("100000")

    def test_calculate_income_tax_splitting(self, service: TaxOptimizationService) -> None:
        """Testet Ehegattensplitting."""
        # Bei gleichem Einkommen sollte Splitting weniger Steuer ergeben
        single_tax = service._calculate_income_tax(Decimal("80000"), is_married=False)
        married_tax = service._calculate_income_tax(Decimal("80000"), is_married=True)
        # Splitting sollte bei typischen Einkommen guenstiger sein
        assert married_tax <= single_tax

    def test_marginal_tax_rate_low_income(self, service: TaxOptimizationService) -> None:
        """Testet Grenzsteuersatz bei niedrigem Einkommen."""
        rate = service._get_marginal_tax_rate(Decimal("15000"))
        assert rate == Decimal("0.14")  # Eingangssteuersatz

    def test_marginal_tax_rate_high_income(self, service: TaxOptimizationService) -> None:
        """Testet Grenzsteuersatz bei hohem Einkommen."""
        rate = service._get_marginal_tax_rate(Decimal("300000"))
        assert rate == Decimal("0.45")  # Reichensteuer


class TestServiceMethods:
    """Tests fuer Service-Methoden-Existenz."""

    @pytest.fixture
    def service(self) -> TaxOptimizationService:
        """Fixture fuer TaxOptimizationService."""
        return get_tax_optimization_service()

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "get_tax_summary existiert nicht im TaxOptimizationService. Die "
            "zusammenfassende Analyse liefert analyze_tax_optimization(...). "
            "Test bleibt als Vertrags-Marker (xfail), bis eine get_tax_summary-"
            "Methode bewusst ergaenzt wird."
        ),
    )
    def test_has_get_tax_summary_method(self, service: TaxOptimizationService) -> None:
        """Testet dass get_tax_summary existiert (nicht im Service vorhanden)."""
        assert hasattr(service, "get_tax_summary")
        assert callable(getattr(service, "get_tax_summary"))

    def test_has_calculate_tax_projection_method(
        self, service: TaxOptimizationService
    ) -> None:
        """Testet dass calculate_tax_projection existiert."""
        assert hasattr(service, "calculate_tax_projection")
        assert callable(getattr(service, "calculate_tax_projection"))

    def test_has_calculate_what_if_scenario_method(
        self, service: TaxOptimizationService
    ) -> None:
        """Testet dass calculate_what_if_scenario existiert."""
        assert hasattr(service, "calculate_what_if_scenario")
        assert callable(getattr(service, "calculate_what_if_scenario"))

    def test_has_prepare_elster_export_method(
        self, service: TaxOptimizationService
    ) -> None:
        """Testet dass prepare_elster_export existiert."""
        assert hasattr(service, "prepare_elster_export")
        assert callable(getattr(service, "prepare_elster_export"))

    def test_has_generate_elster_xml_method(
        self, service: TaxOptimizationService
    ) -> None:
        """Testet dass generate_elster_xml existiert."""
        assert hasattr(service, "generate_elster_xml")
        assert callable(getattr(service, "generate_elster_xml"))

    def test_has_analyze_document_for_tax_method(
        self, service: TaxOptimizationService
    ) -> None:
        """Testet dass analyze_document_for_tax existiert."""
        assert hasattr(service, "analyze_document_for_tax")
        assert callable(getattr(service, "analyze_document_for_tax"))

    def test_has_calculate_afa_for_properties_method(
        self, service: TaxOptimizationService
    ) -> None:
        """Testet dass calculate_afa_for_properties existiert."""
        assert hasattr(service, "calculate_afa_for_properties")
        assert callable(getattr(service, "calculate_afa_for_properties"))

    def test_has_get_personalized_suggestions_method(
        self, service: TaxOptimizationService
    ) -> None:
        """Testet dass get_personalized_suggestions existiert."""
        assert hasattr(service, "get_personalized_suggestions")
        assert callable(getattr(service, "get_personalized_suggestions"))


class TestCategoryMapping:
    """Tests fuer Kategorie-Zuordnung."""

    @pytest.fixture
    def service(self) -> TaxOptimizationService:
        """Fixture fuer TaxOptimizationService."""
        return get_tax_optimization_service()

    def test_category_names_dictionary_exists(self, service: TaxOptimizationService) -> None:
        """Testet dass _category_names Dictionary existiert."""
        assert hasattr(service, "_category_names")
        assert isinstance(service._category_names, dict)

    def test_category_to_german_name(self, service: TaxOptimizationService) -> None:
        """Testet deutsche Kategorie-Namen."""
        mapping = service._category_names

        assert mapping.get(TaxCategory.WERBUNGSKOSTEN) == "Werbungskosten"
        assert mapping.get(TaxCategory.SONDERAUSGABEN) == "Sonderausgaben"
        assert mapping.get(TaxCategory.AUSSERGEWOEHNLICHE_BELASTUNGEN) == "Außergewöhnliche Belastungen"
        assert mapping.get(TaxCategory.HAUSHALTSNAHE_DIENSTLEISTUNGEN) == "Haushaltsnahe Dienstleistungen"
        assert mapping.get(TaxCategory.HANDWERKERLEISTUNGEN) == "Handwerkerleistungen"
        assert mapping.get(TaxCategory.KINDERBETREUUNG) == "Kinderbetreuungskosten"
        assert mapping.get(TaxCategory.SPENDEN) == "Spenden und Mitgliedsbeiträge"

    def test_all_categories_have_german_names(self, service: TaxOptimizationService) -> None:
        """Testet dass alle Kategorien einen deutschen Namen haben."""
        for category in TaxCategory:
            assert category in service._category_names, f"Fehlender Name fuer {category}"
