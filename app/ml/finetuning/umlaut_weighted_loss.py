# -*- coding: utf-8 -*-
"""
Umlaut-Weighted Cross Entropy Loss für Surya OCR Fine-Tuning.

Implementiert eine gewichtete Loss-Funktion, die Umlaut-Fehler
stärker bestraft als reguläre Zeichenfehler.

KRITISCH für deutsche Dokumente:
- ä/a Verwechslungen: 2x Strafe
- ö/o Verwechslungen: 2x Strafe
- ü/u Verwechslungen: 2x Strafe
- ß/ss Verwechslungen: 2x Strafe

Feinpoliert und durchdacht - Enterprise-grade OCR Training.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F
import structlog

logger = structlog.get_logger(__name__)


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class UmlautLossConfig:
    """Konfiguration für Umlaut-gewichtete Loss-Funktion."""

    # Basis-Gewicht für Umlaute (Standard: 2x höhere Strafe)
    umlaut_weight: float = 2.0

    # Gewicht für ß (oft mit ss/sz verwechselt)
    eszett_weight: float = 2.0

    # Gewicht für Großbuchstaben-Umlaute
    capital_umlaut_weight: float = 2.0

    # Label Smoothing für Regularisierung
    label_smoothing: float = 0.1

    # Ignore Index für Padding
    ignore_index: int = -100

    # Zusätzliche Strafe für typische OCR-Verwechslungen
    confusion_penalty: float = 1.5

    # Character-spezifische Gewichte (überschreibt defaults)
    char_weights: Dict[str, float] = field(default_factory=lambda: {
        "ä": 2.0, "ö": 2.0, "ü": 2.0, "ß": 2.0,
        "Ä": 2.0, "Ö": 2.0, "Ü": 2.0,
    })


# =============================================================================
# Umlaut Confusion Matrix
# =============================================================================

# Typische OCR-Verwechslungen bei Umlauten
UMLAUT_CONFUSIONS: Dict[str, List[str]] = {
    # Kleinbuchstaben
    "ä": ["a", "ae", "Ã¤", "ã¤"],
    "ö": ["o", "oe", "Ã¶", "ã¶"],
    "ü": ["u", "ue", "Ã¼", "ã¼"],
    "ß": ["ss", "sz", "B", "Ã", "ÃŸ"],

    # Großbuchstaben
    "Ä": ["A", "Ae", "AE", "Ã„"],
    "Ö": ["O", "Oe", "OE", "Ã–"],
    "Ü": ["U", "Ue", "UE", "Ãœ"],
}

# Inverse Mapping: Welche Zeichen werden oft zu Umlauten?
REVERSE_CONFUSIONS: Dict[str, str] = {}
for umlaut, confusions in UMLAUT_CONFUSIONS.items():
    for confusion in confusions:
        if len(confusion) == 1:  # Nur einzelne Zeichen
            REVERSE_CONFUSIONS[confusion] = umlaut


# =============================================================================
# Loss Functions
# =============================================================================

class UmlautWeightedCrossEntropy(nn.Module):
    """
    Cross-Entropy Loss mit höherer Gewichtung für Umlaut-Fehler.

    Diese Loss-Funktion bestraft typische OCR-Fehler bei deutschen
    Umlauten (ä, ö, ü, ß) stärker als reguläre Zeichenfehler.

    Beispiel:
        - "Müller" → "Muller": Höhere Strafe wegen ü→u
        - "Größe" → "Grosse": Höhere Strafe wegen ö→o und ß→ss
        - "Käse" → "Kase": Höhere Strafe wegen ä→a
    """

    def __init__(
        self,
        vocab_size: int,
        tokenizer: Optional[object] = None,
        config: Optional[UmlautLossConfig] = None,
        device: Optional[str] = None
    ):
        """
        Initialisiert die Loss-Funktion.

        Args:
            vocab_size: Größe des Vokabulars
            tokenizer: Tokenizer für Char-to-ID Mapping
            config: Loss-Konfiguration
            device: Device (cuda/cpu)
        """
        super().__init__()

        self.vocab_size = vocab_size
        self.tokenizer = tokenizer
        self.config = config or UmlautLossConfig()
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")

        # Erstelle Gewichts-Tensor
        self.class_weights = self._build_class_weights()

        # Basis CrossEntropy Loss
        self.ce_loss = nn.CrossEntropyLoss(
            weight=self.class_weights,
            ignore_index=self.config.ignore_index,
            label_smoothing=self.config.label_smoothing,
            reduction='none'  # Für manuelle Aggregation
        )

        # Confusion Penalty Matrix (optional für fortgeschrittene Nutzung)
        self._confusion_indices: Dict[int, List[int]] = {}
        if tokenizer:
            self._build_confusion_indices()

        logger.info(
            "umlaut_weighted_loss_initialized",
            vocab_size=vocab_size,
            umlaut_weight=self.config.umlaut_weight,
            device=self.device
        )

    def _build_class_weights(self) -> torch.Tensor:
        """
        Erstellt Gewichts-Tensor für alle Klassen.

        Umlaute und ß erhalten höhere Gewichte.
        """
        weights = torch.ones(self.vocab_size, device=self.device)

        if self.tokenizer is None:
            logger.warning("Kein Tokenizer - verwende uniforme Gewichte")
            return weights

        # Hole Token-IDs für Umlaute
        for char, weight in self.config.char_weights.items():
            try:
                if hasattr(self.tokenizer, 'encode'):
                    # Standard HuggingFace Tokenizer
                    token_ids = self.tokenizer.encode(char, add_special_tokens=False)
                elif hasattr(self.tokenizer, 'convert_tokens_to_ids'):
                    token_ids = [self.tokenizer.convert_tokens_to_ids(char)]
                else:
                    continue

                for token_id in token_ids:
                    if 0 <= token_id < self.vocab_size:
                        weights[token_id] = weight
                        logger.debug(
                            "umlaut_weight_set",
                            char=char,
                            token_id=token_id,
                            weight=weight
                        )
            except Exception as e:
                logger.warning(f"Konnte Gewicht für '{char}' nicht setzen: {e}")

        return weights

    def _build_confusion_indices(self) -> None:
        """Erstellt Mapping von Umlaut-Token-IDs zu Confusion-Token-IDs."""
        if self.tokenizer is None:
            return

        for umlaut, confusions in UMLAUT_CONFUSIONS.items():
            try:
                umlaut_ids = self.tokenizer.encode(umlaut, add_special_tokens=False)
                confusion_ids = []

                for conf in confusions:
                    if len(conf) == 1:  # Nur einzelne Zeichen
                        conf_ids = self.tokenizer.encode(conf, add_special_tokens=False)
                        confusion_ids.extend(conf_ids)

                for uid in umlaut_ids:
                    self._confusion_indices[uid] = confusion_ids

            except Exception:
                pass

    def forward(
        self,
        logits: torch.Tensor,
        targets: torch.Tensor,
        return_detailed: bool = False
    ) -> torch.Tensor | Tuple[torch.Tensor, Dict[str, float]]:
        """
        Berechnet die gewichtete Loss.

        Args:
            logits: Model-Output (batch_size, seq_len, vocab_size)
            targets: Ground-Truth Labels (batch_size, seq_len)
            return_detailed: Ob detaillierte Metriken zurückgegeben werden sollen

        Returns:
            Loss-Tensor (und optional detaillierte Metriken)
        """
        # Reshape für CrossEntropy: (N, C) und (N,)
        batch_size, seq_len, vocab_size = logits.shape

        logits_flat = logits.view(-1, vocab_size)
        targets_flat = targets.view(-1)

        # Basis Loss pro Token
        token_losses = self.ce_loss(logits_flat, targets_flat)

        # Zusätzliche Strafe für Umlaut-Verwechslungen
        if self._confusion_indices and self.config.confusion_penalty > 1.0:
            token_losses = self._apply_confusion_penalty(
                token_losses, logits_flat, targets_flat
            )

        # Aggregation (ignoriere padding)
        valid_mask = (targets_flat != self.config.ignore_index)
        total_loss = token_losses[valid_mask].sum() / valid_mask.sum().clamp(min=1)

        if return_detailed:
            details = self._compute_detailed_metrics(
                logits_flat, targets_flat, token_losses, valid_mask
            )
            return total_loss, details

        return total_loss

    def _apply_confusion_penalty(
        self,
        losses: torch.Tensor,
        logits: torch.Tensor,
        targets: torch.Tensor
    ) -> torch.Tensor:
        """
        Wendet zusätzliche Strafe für typische Umlaut-Verwechslungen an.

        Wenn das Modell einen Umlaut als typische Verwechslung vorhersagt
        (z.B. 'a' statt 'ä'), wird die Loss erhöht.
        """
        predictions = logits.argmax(dim=-1)

        for umlaut_id, confusion_ids in self._confusion_indices.items():
            # Finde Positionen wo Umlaut erwartet aber Verwechslung vorhergesagt
            umlaut_mask = (targets == umlaut_id)

            if umlaut_mask.any():
                for conf_id in confusion_ids:
                    confusion_mask = umlaut_mask & (predictions == conf_id)
                    if confusion_mask.any():
                        losses[confusion_mask] *= self.config.confusion_penalty

        return losses

    def _compute_detailed_metrics(
        self,
        logits: torch.Tensor,
        targets: torch.Tensor,
        losses: torch.Tensor,
        valid_mask: torch.Tensor
    ) -> Dict[str, float]:
        """Berechnet detaillierte Metriken für Monitoring."""
        predictions = logits.argmax(dim=-1)

        # Basis-Metriken
        valid_targets = targets[valid_mask]
        valid_preds = predictions[valid_mask]
        valid_losses = losses[valid_mask]

        accuracy = (valid_preds == valid_targets).float().mean().item()

        # Umlaut-spezifische Metriken
        umlaut_correct = 0
        umlaut_total = 0

        for umlaut_id in self._confusion_indices.keys():
            umlaut_mask = (valid_targets == umlaut_id)
            if umlaut_mask.any():
                umlaut_total += umlaut_mask.sum().item()
                umlaut_correct += (valid_preds[umlaut_mask] == umlaut_id).sum().item()

        umlaut_accuracy = umlaut_correct / umlaut_total if umlaut_total > 0 else 1.0

        return {
            "total_loss": valid_losses.mean().item(),
            "accuracy": accuracy,
            "umlaut_accuracy": umlaut_accuracy,
            "umlaut_total": umlaut_total,
            "umlaut_correct": umlaut_correct,
        }


class FocalUmlautLoss(UmlautWeightedCrossEntropy):
    """
    Focal Loss Variante mit Umlaut-Gewichtung.

    Kombiniert Focal Loss (für schwer klassifizierbare Beispiele)
    mit Umlaut-Gewichtung (für deutsche OCR).

    Focal Loss: FL(p) = -α * (1-p)^γ * log(p)

    Besonders effektiv wenn:
    - Viele einfache Beispiele (normale Buchstaben)
    - Wenige schwere Beispiele (Umlaute in schwierigen Kontexten)
    """

    def __init__(
        self,
        vocab_size: int,
        tokenizer: Optional[object] = None,
        config: Optional[UmlautLossConfig] = None,
        gamma: float = 2.0,
        alpha: float = 0.25,
        device: Optional[str] = None
    ):
        """
        Args:
            gamma: Fokus-Parameter (höher = mehr Fokus auf schwere Beispiele)
            alpha: Balancing-Faktor
        """
        super().__init__(vocab_size, tokenizer, config, device)
        self.gamma = gamma
        self.alpha = alpha

        logger.info(
            "focal_umlaut_loss_initialized",
            gamma=gamma,
            alpha=alpha
        )

    def forward(
        self,
        logits: torch.Tensor,
        targets: torch.Tensor,
        return_detailed: bool = False
    ) -> torch.Tensor | Tuple[torch.Tensor, Dict[str, float]]:
        """Berechnet Focal Loss mit Umlaut-Gewichtung."""
        batch_size, seq_len, vocab_size = logits.shape

        logits_flat = logits.view(-1, vocab_size)
        targets_flat = targets.view(-1)

        # Softmax Wahrscheinlichkeiten
        probs = F.softmax(logits_flat, dim=-1)

        # Hole Wahrscheinlichkeit für korrekte Klasse
        valid_mask = (targets_flat != self.config.ignore_index)

        # One-hot Encoding für valide Targets
        targets_onehot = F.one_hot(
            targets_flat.clamp(0, vocab_size - 1),
            num_classes=vocab_size
        ).float()

        # Wahrscheinlichkeit für korrektes Label
        pt = (probs * targets_onehot).sum(dim=-1)

        # Focal Weight: (1 - pt)^gamma
        focal_weight = (1 - pt).pow(self.gamma)

        # Cross-Entropy Loss
        ce_loss = F.cross_entropy(
            logits_flat,
            targets_flat.clamp(0, vocab_size - 1),
            weight=self.class_weights,
            reduction='none',
            label_smoothing=self.config.label_smoothing
        )

        # Focal Loss = alpha * focal_weight * CE
        focal_loss = self.alpha * focal_weight * ce_loss

        # Confusion Penalty
        if self._confusion_indices and self.config.confusion_penalty > 1.0:
            focal_loss = self._apply_confusion_penalty(
                focal_loss, logits_flat, targets_flat
            )

        # Aggregation
        total_loss = focal_loss[valid_mask].sum() / valid_mask.sum().clamp(min=1)

        if return_detailed:
            details = self._compute_detailed_metrics(
                logits_flat, targets_flat, focal_loss, valid_mask
            )
            details["avg_focal_weight"] = focal_weight[valid_mask].mean().item()
            return total_loss, details

        return total_loss


# =============================================================================
# Factory Function
# =============================================================================

def create_umlaut_loss(
    vocab_size: int,
    tokenizer: Optional[object] = None,
    loss_type: str = "weighted",
    **kwargs
) -> nn.Module:
    """
    Factory-Funktion für Umlaut-gewichtete Loss-Funktionen.

    Args:
        vocab_size: Vokabular-Größe
        tokenizer: Tokenizer für Character-Mapping
        loss_type: "weighted" oder "focal"
        **kwargs: Zusätzliche Parameter für Loss-Funktion

    Returns:
        Loss-Modul
    """
    config = UmlautLossConfig(**{
        k: v for k, v in kwargs.items()
        if k in UmlautLossConfig.__dataclass_fields__
    })

    if loss_type == "focal":
        gamma = kwargs.get("gamma", 2.0)
        alpha = kwargs.get("alpha", 0.25)
        return FocalUmlautLoss(
            vocab_size=vocab_size,
            tokenizer=tokenizer,
            config=config,
            gamma=gamma,
            alpha=alpha
        )
    else:
        return UmlautWeightedCrossEntropy(
            vocab_size=vocab_size,
            tokenizer=tokenizer,
            config=config
        )


# =============================================================================
# Utility Functions
# =============================================================================

def analyze_umlaut_errors(
    predictions: List[str],
    references: List[str]
) -> Dict[str, int]:
    """
    Analysiert Umlaut-Fehler in Vorhersagen.

    Args:
        predictions: OCR-Vorhersagen
        references: Ground-Truth Texte

    Returns:
        Dictionary mit Fehler-Statistiken
    """
    errors: Dict[str, int] = {
        "total_umlauts": 0,
        "correct_umlauts": 0,
        "missed_umlauts": 0,
        "false_umlauts": 0,
    }

    confusion_counts: Dict[str, Dict[str, int]] = {
        umlaut: {} for umlaut in UMLAUT_CONFUSIONS.keys()
    }

    umlauts = set("äöüÄÖÜß")

    for pred, ref in zip(predictions, references):
        # Zähle Umlaute in Referenz
        for i, char in enumerate(ref):
            if char in umlauts:
                errors["total_umlauts"] += 1

                if i < len(pred):
                    if pred[i] == char:
                        errors["correct_umlauts"] += 1
                    else:
                        errors["missed_umlauts"] += 1
                        # Tracke Verwechslung
                        if pred[i] in UMLAUT_CONFUSIONS.get(char, []):
                            if pred[i] not in confusion_counts[char]:
                                confusion_counts[char][pred[i]] = 0
                            confusion_counts[char][pred[i]] += 1
                else:
                    errors["missed_umlauts"] += 1

        # Zähle False Positives (Umlaute in Prediction aber nicht in Reference)
        for i, char in enumerate(pred):
            if char in umlauts and i < len(ref) and ref[i] != char:
                errors["false_umlauts"] += 1

    errors["confusion_matrix"] = confusion_counts
    errors["accuracy"] = (
        errors["correct_umlauts"] / errors["total_umlauts"]
        if errors["total_umlauts"] > 0 else 1.0
    )

    return errors


def get_umlaut_token_ids(tokenizer: object) -> Dict[str, List[int]]:
    """
    Holt Token-IDs für alle Umlaute.

    Args:
        tokenizer: HuggingFace Tokenizer

    Returns:
        Dict mit Umlaut → Token-IDs Mapping
    """
    result = {}

    for umlaut in "äöüÄÖÜß":
        try:
            if hasattr(tokenizer, 'encode'):
                ids = tokenizer.encode(umlaut, add_special_tokens=False)
            else:
                ids = []
            result[umlaut] = ids
        except Exception:
            result[umlaut] = []

    return result
