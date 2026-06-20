# -*- coding: utf-8 -*-
"""
SHAP Erklärbarkeit für ML-Routing.

Erklärt warum bestimmte OCR-Backends gewählt wurden:
- Feature Importance (global)
- SHAP Values (lokal pro Entscheidung)
- Kontrafaktische Erklärungen
- Visualisierungen

Feinpoliert und durchdacht - Transparente KI-Entscheidungen.
"""

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import structlog
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)

# Thread-Safety für Singleton
_shap_explainer_lock = threading.Lock()

# Optional SHAP integration
SHAP_AVAILABLE = False
try:
    import shap

    SHAP_AVAILABLE = True
except ImportError:
    logger.info("SHAP nicht installiert - verwende eingebaute Feature Importance")


@dataclass
class FeatureContribution:
    """Beitrag eines Features zur Entscheidung."""
    feature_name: str
    feature_value: object
    shap_value: float  # Positiv = erhöht Wahrscheinlichkeit, Negativ = verringert
    contribution_percent: float  # Relativer Beitrag in %
    direction: str  # "supports" oder "opposes"
    german_explanation: str


@dataclass
class RoutingExplanation:
    """Vollständige Erklärung einer Routing-Entscheidung."""
    timestamp: datetime
    document_id: str
    selected_backend: str
    confidence: float
    top_contributions: List[FeatureContribution]
    alternative_backends: List[Tuple[str, float]]  # (backend, probability)
    decision_summary: str  # Deutsche Zusammenfassung
    counterfactual: Optional[str]  # "Wenn X, dann wäre Y gewählt worden"
    metadata: Dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        """Konvertiere zu Dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "document_id": self.document_id,
            "selected_backend": self.selected_backend,
            "confidence": self.confidence,
            "top_contributions": [
                {
                    "feature_name": fc.feature_name,
                    "feature_value": fc.feature_value,
                    "shap_value": fc.shap_value,
                    "contribution_percent": fc.contribution_percent,
                    "direction": fc.direction,
                    "explanation": fc.german_explanation,
                }
                for fc in self.top_contributions
            ],
            "alternative_backends": self.alternative_backends,
            "decision_summary": self.decision_summary,
            "counterfactual": self.counterfactual,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        """Serialisiere zu JSON."""
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


class SHAPExplainer:
    """
    SHAP-basierte Erklärungen für OCR-Routing.

    Features:
    - TreeExplainer für XGBoost-Modelle
    - Feature Importance Ranking
    - Lokale Erklärungen pro Entscheidung
    - Kontrafaktische Analyse
    - Deutsche Textgenerierung
    """

    # Feature-Beschreibungen auf Deutsch
    FEATURE_DESCRIPTIONS = {
        "document_type": {
            "name": "Dokumenttyp",
            "values": {
                "invoice": "Rechnung",
                "contract": "Vertrag",
                "letter": "Brief",
                "form": "Formular",
                "report": "Bericht",
                "other": "Sonstiges",
            },
        },
        "complexity": {
            "name": "Komplexität",
            "values": {
                "low": "niedrig",
                "medium": "mittel",
                "high": "hoch",
            },
        },
        "quality_score": {
            "name": "Bildqualität",
            "unit": "%",
        },
        "has_tables": {
            "name": "Enthält Tabellen",
            "values": {True: "ja", False: "nein"},
        },
        "has_formulas": {
            "name": "Enthält Formeln",
            "values": {True: "ja", False: "nein"},
        },
        "has_handwriting": {
            "name": "Enthält Handschrift",
            "values": {True: "ja", False: "nein"},
        },
        "detected_language": {
            "name": "Sprache",
            "values": {
                "de": "Deutsch",
                "en": "Englisch",
                "pl": "Polnisch",
                "ru": "Russisch",
                "uk": "Ukrainisch",
            },
        },
        "file_size_mb": {
            "name": "Dateigröße",
            "unit": "MB",
        },
        "page_count": {
            "name": "Seitenanzahl",
            "unit": "Seiten",
        },
        "dpi": {
            "name": "Auflösung",
            "unit": "DPI",
        },
    }

    # Backend-Beschreibungen auf Deutsch
    BACKEND_DESCRIPTIONS = {
        "deepseek": "DeepSeek (beste Genauigkeit für deutsche Dokumente)",
        "got_ocr": "GOT-OCR (schnell, gut für Tabellen)",
        "surya": "Surya (CPU-basiert, Layout-Analyse)",
        "surya_gpu": "Surya GPU (schnelle GPU-Variante)",
        "donut": "Donut (multilinguale Dokumente)",
        "tesseract": "Tesseract (Fallback-Option)",
    }

    def __init__(
        self,
        model: Optional[object] = None,
        feature_names: Optional[List[str]] = None,
        storage_path: Optional[Path] = None,
    ) -> None:
        """
        Initialisiere SHAP Explainer.

        Args:
            model: Trainiertes ML-Modell (XGBoost)
            feature_names: Liste der Feature-Namen
            storage_path: Pfad für Erklärungen
        """
        self.model = model
        self.feature_names = feature_names or []
        self.storage_path = storage_path or Path("/tmp/ablage_ml/explanations")
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self._shap_explainer: Optional[object] = None
        self._global_importance: Optional[Dict[str, float]] = None

        # Cache für Erklärungen
        self._explanation_cache: Dict[str, RoutingExplanation] = {}

        if model and SHAP_AVAILABLE:
            self._initialize_shap_explainer()

    def _initialize_shap_explainer(self) -> None:
        """Initialisiere SHAP TreeExplainer."""
        if not SHAP_AVAILABLE or not self.model:
            return

        try:
            self._shap_explainer = shap.TreeExplainer(self.model)
            logger.info("SHAP TreeExplainer initialisiert")
        except Exception as e:
            logger.warning("shap_explainer_init_fehlgeschlagen", **safe_error_log(e))

    def set_model(self, model: object, feature_names: List[str]) -> None:
        """
        Setze oder aktualisiere das Modell.

        Args:
            model: Trainiertes ML-Modell
            feature_names: Feature-Namen in korrekter Reihenfolge

        Raises:
            ValueError: Bei ungültigen Parametern
        """
        if model is None:
            raise ValueError("model darf nicht None sein")

        if not feature_names or not isinstance(feature_names, list):
            raise ValueError("feature_names muss eine nicht-leere Liste sein")
        if len(feature_names) > 100:
            raise ValueError("feature_names darf maximal 100 Features haben")

        # Validate feature names are strings
        for i, name in enumerate(feature_names):
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"feature_names[{i}] muss ein nicht-leerer String sein")

        self.model = model
        self.feature_names = [n.strip() for n in feature_names]
        self._global_importance = None

        if SHAP_AVAILABLE:
            self._initialize_shap_explainer()

    def explain_routing(
        self,
        document_id: str,
        features: Dict[str, object],
        selected_backend: str,
        confidence: float,
        all_probabilities: Dict[str, float],
    ) -> RoutingExplanation:
        """
        Erkläre eine Routing-Entscheidung.

        Args:
            document_id: Dokument-ID
            features: Feature-Dictionary
            selected_backend: Gewähltes Backend
            confidence: Konfidenz der Entscheidung
            all_probabilities: Wahrscheinlichkeiten aller Backends

        Returns:
            RoutingExplanation mit detaillierter Erklärung

        Raises:
            ValueError: Bei ungültigen Parametern
        """
        # Input Validation
        if not document_id or not isinstance(document_id, str):
            raise ValueError("document_id muss ein nicht-leerer String sein")
        document_id = document_id.strip()
        if len(document_id) > 100:
            raise ValueError("document_id darf maximal 100 Zeichen haben")

        if not isinstance(features, dict):
            raise ValueError("features muss ein Dictionary sein")

        if not selected_backend or not isinstance(selected_backend, str):
            raise ValueError("selected_backend muss ein nicht-leerer String sein")
        selected_backend = selected_backend.strip()

        if not isinstance(confidence, (int, float)):
            raise ValueError("confidence muss eine Zahl sein")
        # Clamp confidence to valid range
        confidence = max(0.0, min(1.0, float(confidence)))

        if not isinstance(all_probabilities, dict):
            raise ValueError("all_probabilities muss ein Dictionary sein")

        # Calculate contributions
        contributions = self._calculate_contributions(features, selected_backend)

        # Get alternatives
        alternatives = sorted(
            [(k, v) for k, v in all_probabilities.items() if k != selected_backend],
            key=lambda x: x[1],
            reverse=True,
        )[:3]

        # Generate summary
        summary = self._generate_summary(
            selected_backend, confidence, contributions[:3]
        )

        # Generate counterfactual
        counterfactual = self._generate_counterfactual(
            features, selected_backend, alternatives
        )

        explanation = RoutingExplanation(
            timestamp=datetime.now(),
            document_id=document_id,
            selected_backend=selected_backend,
            confidence=confidence,
            top_contributions=contributions[:5],
            alternative_backends=alternatives,
            decision_summary=summary,
            counterfactual=counterfactual,
            metadata={
                "shap_available": SHAP_AVAILABLE,
                "model_available": self.model is not None,
            },
        )

        # Cache and store
        self._explanation_cache[document_id] = explanation
        self._store_explanation(explanation)

        return explanation

    def _calculate_contributions(
        self,
        features: Dict[str, object],
        selected_backend: str,
    ) -> List[FeatureContribution]:
        """Berechne Feature-Beiträge zur Entscheidung."""
        contributions = []

        if self._shap_explainer and self.model:
            # Use SHAP values
            contributions = self._calculate_shap_contributions(features, selected_backend)
        else:
            # Fallback to heuristic importance
            contributions = self._calculate_heuristic_contributions(
                features, selected_backend
            )

        # Sort by absolute contribution
        contributions.sort(key=lambda x: abs(x.shap_value), reverse=True)

        return contributions

    def _calculate_shap_contributions(
        self,
        features: Dict[str, object],
        selected_backend: str,
    ) -> List[FeatureContribution]:
        """Berechne SHAP-basierte Beiträge."""
        contributions = []

        try:
            # Prepare feature array
            feature_array = np.array([
                [features.get(name, 0) for name in self.feature_names]
            ])

            # Get SHAP values
            shap_values = self._shap_explainer.shap_values(feature_array)

            # Get backend index
            backend_names = list(self.model.classes_) if hasattr(self.model, 'classes_') else []
            backend_idx = backend_names.index(selected_backend) if selected_backend in backend_names else 0

            # Extract values for selected backend
            if isinstance(shap_values, list):
                values = shap_values[backend_idx][0]
            else:
                values = shap_values[0]

            # Calculate total for percentage
            total = sum(abs(v) for v in values) or 1.0

            for i, (name, value) in enumerate(zip(self.feature_names, values)):
                feature_value = features.get(name, "unbekannt")
                contribution = FeatureContribution(
                    feature_name=name,
                    feature_value=feature_value,
                    shap_value=float(value),
                    contribution_percent=abs(value) / total * 100,
                    direction="supports" if value > 0 else "opposes",
                    german_explanation=self._generate_feature_explanation(
                        name, feature_value, value
                    ),
                )
                contributions.append(contribution)

        except Exception as e:
            logger.warning("shap_berechnung_fehlgeschlagen", **safe_error_log(e))
            contributions = self._calculate_heuristic_contributions(
                features, selected_backend
            )

        return contributions

    def _calculate_heuristic_contributions(
        self,
        features: Dict[str, object],
        selected_backend: str,
    ) -> List[FeatureContribution]:
        """Berechne heuristische Feature-Beiträge ohne SHAP."""
        contributions = []

        # Heuristic importance weights
        importance_weights = {
            "complexity": 0.25,
            "detected_language": 0.20,
            "has_tables": 0.15,
            "has_formulas": 0.12,
            "quality_score": 0.10,
            "has_handwriting": 0.08,
            "document_type": 0.05,
            "file_size_mb": 0.03,
            "page_count": 0.02,
        }

        total_weight = sum(importance_weights.values())

        for name, weight in importance_weights.items():
            feature_value = features.get(name, "unbekannt")

            # Determine direction based on backend preferences
            supports = self._feature_supports_backend(name, feature_value, selected_backend)
            shap_value = weight if supports else -weight * 0.5

            contribution = FeatureContribution(
                feature_name=name,
                feature_value=feature_value,
                shap_value=shap_value,
                contribution_percent=abs(weight) / total_weight * 100,
                direction="supports" if supports else "opposes",
                german_explanation=self._generate_feature_explanation(
                    name, feature_value, shap_value
                ),
            )
            contributions.append(contribution)

        return contributions

    def _feature_supports_backend(
        self,
        feature_name: str,
        feature_value: object,
        backend: str,
    ) -> bool:
        """Bestimme ob Feature das gewählte Backend unterstützt."""
        # Backend preferences
        preferences = {
            "deepseek": {
                "complexity": ["high"],
                "detected_language": ["de"],
                "has_handwriting": [True],
            },
            "got_ocr": {
                "has_tables": [True],
                "has_formulas": [True],
                "complexity": ["medium"],
            },
            "donut": {
                "detected_language": ["pl", "ru", "uk"],
            },
            "surya": {
                "complexity": ["low"],
            },
        }

        backend_prefs = preferences.get(backend, {})
        feature_prefs = backend_prefs.get(feature_name, [])

        return feature_value in feature_prefs

    def _generate_feature_explanation(
        self,
        feature_name: str,
        feature_value: object,
        shap_value: float,
    ) -> str:
        """Generiere deutsche Erklärung für Feature-Beitrag."""
        desc = self.FEATURE_DESCRIPTIONS.get(feature_name, {})
        german_name = desc.get("name", feature_name)

        # Format value
        if "values" in desc and feature_value in desc["values"]:
            german_value = desc["values"][feature_value]
        elif "unit" in desc:
            german_value = f"{feature_value} {desc['unit']}"
        else:
            german_value = str(feature_value)

        # Generate explanation
        if shap_value > 0.1:
            return f"{german_name} ({german_value}) spricht stark für diese Wahl"
        elif shap_value > 0:
            return f"{german_name} ({german_value}) unterstützt diese Entscheidung"
        elif shap_value < -0.1:
            return f"{german_name} ({german_value}) spricht eher dagegen"
        else:
            return f"{german_name} ({german_value}) hat geringen Einfluss"

    def _generate_summary(
        self,
        backend: str,
        confidence: float,
        top_contributions: List[FeatureContribution],
    ) -> str:
        """Generiere deutsche Zusammenfassung der Entscheidung."""
        backend_desc = self.BACKEND_DESCRIPTIONS.get(backend, backend)
        confidence_pct = int(confidence * 100)

        # Build summary
        summary_parts = [
            f"{backend_desc} wurde mit {confidence_pct}% Konfidenz gewählt."
        ]

        if top_contributions:
            reasons = [fc.german_explanation for fc in top_contributions[:2]]
            summary_parts.append("Hauptgründe: " + "; ".join(reasons) + ".")

        return " ".join(summary_parts)

    def _generate_counterfactual(
        self,
        features: Dict[str, object],
        selected_backend: str,
        alternatives: List[Tuple[str, float]],
    ) -> Optional[str]:
        """Generiere kontrafaktische Erklärung."""
        if not alternatives:
            return None

        alt_backend, alt_prob = alternatives[0]

        # Find most influential feature that could change decision
        key_features = ["complexity", "detected_language", "has_tables"]

        for feature in key_features:
            current_value = features.get(feature)

            # What value would favor the alternative?
            if feature == "detected_language":
                if alt_backend == "donut" and current_value not in ["pl", "ru", "uk"]:
                    return (
                        f"Wäre die Sprache Polnisch/Russisch/Ukrainisch, "
                        f"würde {self.BACKEND_DESCRIPTIONS.get(alt_backend, alt_backend)} "
                        f"bevorzugt werden."
                    )
            elif feature == "complexity":
                if alt_backend == "deepseek" and current_value != "high":
                    return (
                        f"Bei höherer Dokumentkomplexität würde "
                        f"{self.BACKEND_DESCRIPTIONS.get(alt_backend, alt_backend)} "
                        f"gewählt werden."
                    )

        return None

    def get_global_importance(self) -> Dict[str, float]:
        """Hole globale Feature Importance."""
        if self._global_importance:
            return self._global_importance

        if self.model and hasattr(self.model, 'feature_importances_'):
            importances = self.model.feature_importances_
            self._global_importance = {
                name: float(imp)
                for name, imp in zip(self.feature_names, importances)
            }
        else:
            # Default importance
            self._global_importance = {
                "complexity": 0.25,
                "detected_language": 0.20,
                "has_tables": 0.15,
                "has_formulas": 0.12,
                "quality_score": 0.10,
                "has_handwriting": 0.08,
                "document_type": 0.05,
                "file_size_mb": 0.03,
                "page_count": 0.02,
            }

        return self._global_importance

    def get_explanation(self, document_id: str) -> Optional[RoutingExplanation]:
        """Hole gespeicherte Erklärung für Dokument."""
        return self._explanation_cache.get(document_id)

    def _store_explanation(self, explanation: RoutingExplanation) -> None:
        """Speichere Erklärung als JSON."""
        filename = f"explanation_{explanation.document_id}_{explanation.timestamp.strftime('%Y%m%d_%H%M%S')}.json"
        filepath = self.storage_path / filename

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(explanation.to_json())


# Singleton instance
_shap_explainer: Optional[SHAPExplainer] = None


def get_shap_explainer() -> SHAPExplainer:
    """
    Hole globale SHAPExplainer Instanz.

    Thread-safe mit double-checked locking.
    """
    global _shap_explainer

    # Fast path: bereits initialisiert
    if _shap_explainer is not None:
        return _shap_explainer

    # Slow path: Thread-safe Initialisierung
    with _shap_explainer_lock:
        # Double-check nach Lock-Erwerb
        if _shap_explainer is None:
            logger.info("shap_explainer_initialisierung")
            _shap_explainer = SHAPExplainer()
            logger.info(
                "shap_explainer_initialisiert",
                shap_available=SHAP_AVAILABLE,
                model_loaded=_shap_explainer.model is not None,
            )

    return _shap_explainer
