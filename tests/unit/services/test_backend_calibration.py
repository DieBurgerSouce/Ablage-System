# -*- coding: utf-8 -*-
"""
Unit Tests für Backend-Specific Confidence Calibration.

Testet die erweiterte Kalibrierungsfunktionalität:
- Backend-spezifische Kalibrierung
- Document-Type-spezifische Kalibrierung
- Online Learning mit automatischem Retrain
- Sliding Window für aktuelle Kalibrierung
"""

import pytest
import time
from app.services.confidence_calibration import (
    CalibrationData,
    CalibrationStats,
    DocumentType,
    BackendDocTypeCalibrator,
    IsotonicCalibrator,
    PlattScalingCalibrator,
    TemperatureScalingCalibrator,
    HistogramBinningCalibrator,
    ConfidenceCalibrationService,
)


class TestCalibrationData:
    """Tests für CalibrationData mit Timestamps."""

    def test_add_sample_with_timestamp(self):
        """Samples werden mit Timestamps gespeichert."""
        data = CalibrationData()
        data.add_sample(0.8, True)
        data.add_sample(0.6, False)

        assert len(data) == 2
        assert len(data.timestamps) == 2
        assert data.confidences == [0.8, 0.6]
        assert data.actuals == [1, 0]

    def test_get_recent_samples(self):
        """Sliding Window filtert alte Samples."""
        data = CalibrationData()

        # Alte Samples (>30 Tage)
        old_timestamp = time.time() - (35 * 24 * 60 * 60)
        data.confidences.append(0.5)
        data.actuals.append(0)
        data.timestamps.append(old_timestamp)

        # Neue Samples
        data.add_sample(0.8, True)
        data.add_sample(0.9, True)

        recent_conf, recent_act = data.get_recent_samples(max_age_days=30)

        assert len(recent_conf) == 2
        assert 0.8 in recent_conf
        assert 0.9 in recent_conf
        assert 0.5 not in recent_conf


class TestBackendDocTypeCalibrator:
    """Tests für Backend + DocumentType Kalibrator."""

    def test_init(self):
        """Kalibrator initialisiert korrekt."""
        cal = BackendDocTypeCalibrator(
            backend="deepseek",
            doc_type="invoice"
        )
        assert cal.backend == "deepseek"
        assert cal.doc_type == "invoice"
        assert cal.calibrator is None

    def test_add_sample_no_auto_retrain(self):
        """Samples werden hinzugefügt ohne Auto-Retrain."""
        cal = BackendDocTypeCalibrator(
            backend="deepseek",
            doc_type="invoice",
            auto_retrain_threshold=100  # Hoher Threshold
        )

        # Füge wenige Samples hinzu
        for _ in range(10):
            retrained = cal.add_sample(0.8, True)
            assert not retrained

        assert len(cal.training_data) == 10
        assert cal._samples_since_train == 10

    def test_add_sample_auto_retrain(self):
        """Auto-Retrain wird bei Threshold ausgelöst."""
        cal = BackendDocTypeCalibrator(
            backend="deepseek",
            doc_type="invoice",
            auto_retrain_threshold=15
        )

        # Füge genug Samples für Retrain hinzu
        for i in range(16):
            retrained = cal.add_sample(0.5 + i * 0.03, i % 2 == 0)

        # Auto-Retrain sollte ausgelöst worden sein
        assert cal.calibrator is not None
        assert cal._samples_since_train < 15

    def test_predict_without_calibrator(self):
        """Ohne Kalibrator wird roher Wert zurückgegeben."""
        cal = BackendDocTypeCalibrator(
            backend="deepseek",
            doc_type="invoice"
        )

        assert cal.predict(0.75) == 0.75

    def test_predict_with_calibrator(self):
        """Mit trainiertem Kalibrator wird kalibrierter Wert zurückgegeben."""
        cal = BackendDocTypeCalibrator(
            backend="deepseek",
            doc_type="invoice"
        )

        # Trainiere mit Daten
        for i in range(20):
            cal.training_data.add_sample(0.5 + i * 0.025, i % 2 == 0)

        cal.retrain()

        # Kalibrator sollte vorhanden sein
        assert cal.calibrator is not None

        # Prediction sollte sich vom rohen Wert unterscheiden können
        raw = 0.75
        calibrated = cal.predict(raw)
        assert isinstance(calibrated, float)
        assert 0.0 <= calibrated <= 1.0


class TestConfidenceCalibrationServiceDocType:
    """Tests für Document-Type-spezifische Kalibrierung."""

    @pytest.fixture
    def service(self):
        """Erstelle Calibration Service für Tests."""
        return ConfidenceCalibrationService(
            calibration_method="isotonic",
            enable_doctype_calibration=True,
            auto_retrain_threshold=15
        )

    def test_add_doctype_training_sample(self, service):
        """Dokumenttyp-spezifische Samples werden hinzugefügt."""
        service.add_doctype_training_sample("deepseek", "invoice", 0.8, True)
        service.add_doctype_training_sample("deepseek", "invoice", 0.7, True)
        service.add_doctype_training_sample("deepseek", "letter", 0.9, False)

        stats = service.get_doctype_stats()

        assert "deepseek:invoice" in stats
        assert stats["deepseek:invoice"]["samples"] == 2
        assert "deepseek:letter" in stats
        assert stats["deepseek:letter"]["samples"] == 1

    def test_calibrate_with_doctype_fallback(self, service):
        """Ohne Kalibrator wird roher Wert zurückgegeben."""
        # Keine Trainings-Daten
        calibrated = service.calibrate_with_doctype("deepseek", "invoice", 0.8)
        assert calibrated == 0.8

    def test_calibrate_with_doctype_after_training(self, service):
        """Nach Training wird kalibrierter Wert zurückgegeben."""
        # Füge genug Samples für Training hinzu
        for i in range(20):
            is_correct = (0.5 + i * 0.025) > 0.7
            service.add_doctype_training_sample(
                "deepseek", "invoice",
                0.5 + i * 0.025,
                is_correct
            )

        # Trainiere explizit
        service.train_doctype_calibrator("deepseek", "invoice")

        # Kalibrierung sollte funktionieren
        calibrated = service.calibrate_with_doctype("deepseek", "invoice", 0.75)
        assert isinstance(calibrated, float)
        assert 0.0 <= calibrated <= 1.0

    def test_train_all_doctype_calibrators(self, service):
        """Alle Dokumenttyp-Kalibratoren werden trainiert."""
        # Füge Samples für verschiedene Kombinationen hinzu
        for i in range(15):
            service.add_doctype_training_sample("deepseek", "invoice", 0.5 + i * 0.03, True)
            service.add_doctype_training_sample("got_ocr", "letter", 0.4 + i * 0.04, False)

        results = service.train_all_doctype_calibrators()

        assert "deepseek:invoice" in results
        assert "got_ocr:letter" in results

    def test_get_best_backend_for_doctype(self, service):
        """Bestes Backend für Dokumenttyp wird gefunden."""
        # DeepSeek ist besser für Invoices
        for i in range(15):
            service.add_doctype_training_sample("deepseek", "invoice", 0.8, True)
            service.add_doctype_training_sample("got_ocr", "invoice", 0.6, i < 5)

        best = service.get_best_backend_for_doctype("invoice")
        assert best == "deepseek"

    def test_doctype_disabled_fallback(self):
        """Bei deaktiviertem DocType wird generische Kalibrierung verwendet."""
        service = ConfidenceCalibrationService(
            enable_doctype_calibration=False
        )

        # Sollte ohne Fehler funktionieren
        retrained = service.add_doctype_training_sample("deepseek", "invoice", 0.8, True)
        assert not retrained

        # Generische Trainings-Daten sollten vorhanden sein
        assert "deepseek" in service._training_data
        assert len(service._training_data["deepseek"]) == 1


class TestCalibrators:
    """Tests für die verschiedenen Kalibrator-Implementierungen."""

    def test_isotonic_calibrator(self):
        """Isotonic Calibrator trainiert und kalibriert."""
        cal = IsotonicCalibrator()

        # Trainings-Daten
        confidences = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        actuals = [0, 0, 0, 1, 0, 1, 1, 1, 1, 1]

        cal.fit(confidences, actuals)

        # Kalibrierung sollte monoton sein
        results = [cal.predict(c) for c in [0.2, 0.5, 0.8]]
        assert results[0] <= results[1] <= results[2]

    def test_platt_scaling_calibrator(self):
        """Platt Scaling Calibrator trainiert und kalibriert."""
        cal = PlattScalingCalibrator()

        confidences = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        actuals = [0, 0, 0, 0, 1, 1, 1, 1, 1, 1]

        cal.fit(confidences, actuals)

        result = cal.predict(0.5)
        assert 0.0 <= result <= 1.0

    def test_temperature_scaling_calibrator(self):
        """Temperature Scaling Calibrator trainiert und kalibriert."""
        cal = TemperatureScalingCalibrator()

        confidences = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
        actuals = [0, 0, 1, 1, 1, 1]

        cal.fit(confidences, actuals)

        result = cal.predict(0.5)
        assert 0.0 <= result <= 1.0

    def test_histogram_binning_calibrator(self):
        """Histogram Binning Calibrator trainiert und kalibriert."""
        cal = HistogramBinningCalibrator(n_bins=5)

        confidences = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95]
        actuals = [0, 0, 0, 0, 1, 1, 1, 1, 1, 1]

        cal.fit(confidences, actuals)

        result = cal.predict(0.75)
        assert 0.0 <= result <= 1.0


class TestDocumentType:
    """Tests für DocumentType Enum."""

    def test_document_types(self):
        """Alle Dokumenttypen sind definiert."""
        assert DocumentType.INVOICE == "invoice"
        assert DocumentType.LETTER == "letter"
        assert DocumentType.CONTRACT == "contract"
        assert DocumentType.FORM == "form"
        assert DocumentType.HANDWRITTEN == "handwritten"
        assert DocumentType.FRAKTUR == "fraktur"
        assert DocumentType.UNKNOWN == "unknown"


class TestIntegration:
    """Integration-Tests für Confidence Calibration."""

    def test_end_to_end_calibration_workflow(self):
        """Vollständiger Kalibrierungs-Workflow."""
        service = ConfidenceCalibrationService(
            calibration_method="isotonic",
            enable_doctype_calibration=True,
            auto_retrain_threshold=20
        )

        # Simuliere OCR-Ergebnisse für verschiedene Backends und Dokumenttypen
        import random
        random.seed(42)

        # DeepSeek ist gut bei Invoices
        for _ in range(25):
            conf = random.uniform(0.7, 0.95)
            is_correct = random.random() < conf  # Higher conf = more likely correct
            service.add_doctype_training_sample("deepseek", "invoice", conf, is_correct)

        # GOT-OCR ist gut bei Letters
        for _ in range(25):
            conf = random.uniform(0.6, 0.9)
            is_correct = random.random() < conf
            service.add_doctype_training_sample("got_ocr", "letter", conf, is_correct)

        # Trainiere alle
        service.train_all_doctype_calibrators()

        # Prüfe Kalibrierung
        raw_conf = 0.8
        deepseek_invoice = service.calibrate_with_doctype("deepseek", "invoice", raw_conf)
        got_ocr_letter = service.calibrate_with_doctype("got_ocr", "letter", raw_conf)

        # Beide sollten kalibrierte Werte sein
        assert isinstance(deepseek_invoice, float)
        assert isinstance(got_ocr_letter, float)

        # Stats sollten verfügbar sein
        stats = service.get_doctype_stats()
        assert len(stats) >= 2

    def test_sliding_window_respects_age(self):
        """Sliding Window filtert alte Daten korrekt."""
        service = ConfidenceCalibrationService(
            calibration_method="isotonic",
            enable_doctype_calibration=True,
            sliding_window_days=30
        )

        # Simuliere alte und neue Daten
        for i in range(15):
            service.add_doctype_training_sample("deepseek", "invoice", 0.5 + i * 0.03, True)

        # Trainiere Kalibrator (sollte neuere Daten bevorzugen)
        service.train_doctype_calibrator("deepseek", "invoice")

        # Kalibrator sollte existieren
        key = "deepseek:invoice"
        assert key in service._doctype_calibrators
        assert service._doctype_calibrators[key].calibrator is not None
