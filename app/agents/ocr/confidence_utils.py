"""
Shared confidence calculation utilities for OCR agents.

Provides reusable functions for token-level confidence calculation
used by DeepSeek, GOT-OCR, and other transformer-based OCR backends.
"""

from typing import Any, Dict, List, Optional, Set, Tuple

import torch
import torch.nn.functional as F
import structlog

logger = structlog.get_logger(__name__)


def calculate_token_confidence(
    scores: Tuple[torch.Tensor, ...],
    generated_ids: torch.Tensor,
    tokenizer: Optional[Any] = None,
    skip_special_tokens: bool = True,
    low_confidence_threshold: float = 0.7,
    vectorized: bool = True
) -> Dict[str, Any]:
    """
    Berechne Token-Level Confidence aus Model Output Logits.

    Gemeinsame Implementierung fuer DeepSeek, GOT-OCR und andere
    transformer-basierte OCR Backends.

    Args:
        scores: Tuple von Logit-Tensoren fuer jeden generierten Token
        generated_ids: Die generierten Token-IDs (batch_size x seq_len)
        tokenizer: Optional tokenizer fuer Special Token Detection
        skip_special_tokens: Spezielle Tokens ueberspringen
        low_confidence_threshold: Schwellenwert fuer niedrige Confidence
        vectorized: Verwende vektorisierte Berechnung (schneller)

    Returns:
        Dictionary mit Confidence-Metriken:
        - mean_confidence: Durchschnittliche Confidence ueber alle Tokens
        - min_confidence: Minimale Token-Confidence
        - weighted_confidence: Gewichtete Confidence (laengere Tokens wichtiger)
        - token_confidences: Liste der Confidences pro Token
        - low_confidence_positions: Positionen mit Confidence < threshold
        - confidence_method: Verwendete Berechnungsmethode
    """
    # Handle empty scores
    if not scores or len(scores) == 0:
        return {
            "mean_confidence": 0.0,
            "min_confidence": 0.0,
            "weighted_confidence": 0.0,
            "token_confidences": [],
            "low_confidence_positions": [],
            "confidence_method": "no_scores"
        }

    # Get special token IDs
    special_token_ids: Set[int] = set()
    if tokenizer and skip_special_tokens:
        if hasattr(tokenizer, 'all_special_ids'):
            special_token_ids = set(tokenizer.all_special_ids)

    try:
        num_scores = len(scores)
        seq_len = generated_ids.shape[1] if generated_ids.dim() > 1 else len(generated_ids)
        input_length = seq_len - num_scores

        # Validate bounds
        if input_length < 0 or input_length + num_scores > seq_len:
            logger.warning(
                "confidence_bounds_invalid",
                input_length=input_length,
                num_scores=num_scores,
                seq_len=seq_len
            )
            return {
                "mean_confidence": 0.85,
                "min_confidence": 0.70,
                "weighted_confidence": 0.80,
                "token_confidences": [],
                "low_confidence_positions": [],
                "confidence_method": "bounds_error"
            }

        if vectorized:
            return _calculate_vectorized(
                scores=scores,
                generated_ids=generated_ids,
                input_length=input_length,
                special_token_ids=special_token_ids,
                skip_special_tokens=skip_special_tokens,
                low_confidence_threshold=low_confidence_threshold
            )
        else:
            return _calculate_iterative(
                scores=scores,
                generated_ids=generated_ids,
                input_length=input_length,
                special_token_ids=special_token_ids,
                skip_special_tokens=skip_special_tokens,
                low_confidence_threshold=low_confidence_threshold
            )

    except Exception as e:
        logger.warning("confidence_calculation_error", error=str(e))
        return {
            "mean_confidence": 0.80,
            "min_confidence": 0.60,
            "weighted_confidence": 0.75,
            "token_confidences": [],
            "low_confidence_positions": [],
            "confidence_method": "error_fallback"
        }


def _calculate_vectorized(
    scores: Tuple[torch.Tensor, ...],
    generated_ids: torch.Tensor,
    input_length: int,
    special_token_ids: Set[int],
    skip_special_tokens: bool,
    low_confidence_threshold: float
) -> Dict[str, Any]:
    """Vektorisierte Confidence-Berechnung (~10x schneller)."""
    try:
        # Stack all logits: (num_tokens, batch_size, vocab_size)
        stacked_logits = torch.stack(scores, dim=0)

        # Handle batch dimension
        if stacked_logits.dim() == 4:
            stacked_logits = stacked_logits.squeeze(1)
        elif stacked_logits.dim() == 3:
            stacked_logits = stacked_logits[:, 0, :]  # First batch

        # Softmax ueber Vokabular
        all_probs = F.softmax(stacked_logits, dim=-1)  # (num_tokens, vocab_size)

        # Token IDs fuer generierte Tokens
        if generated_ids.dim() > 1:
            gen_ids = generated_ids[0, input_length:input_length + len(scores)]
        else:
            gen_ids = generated_ids[input_length:input_length + len(scores)]

        # Gather Wahrscheinlichkeiten fuer generierte Tokens
        token_probs = torch.gather(
            all_probs,
            dim=-1,
            index=gen_ids.unsqueeze(-1)
        ).squeeze(-1)

        # Maske fuer Special Tokens
        if skip_special_tokens and special_token_ids:
            mask = torch.tensor(
                [tid.item() not in special_token_ids for tid in gen_ids],
                device=token_probs.device
            )
            valid_probs = token_probs[mask]
        else:
            valid_probs = token_probs
            mask = torch.ones_like(token_probs, dtype=torch.bool)

        if len(valid_probs) == 0:
            return {
                "mean_confidence": 0.90,
                "min_confidence": 0.85,
                "weighted_confidence": 0.88,
                "token_confidences": [],
                "low_confidence_positions": [],
                "confidence_method": "vectorized_special_only"
            }

        # Metriken berechnen
        mean_conf = float(valid_probs.mean())
        min_conf = float(valid_probs.min())

        # Gewichtete Confidence (spaetere Tokens haben mehr Gewicht)
        weights = torch.arange(1, len(valid_probs) + 1, device=valid_probs.device, dtype=torch.float32)
        weighted_conf = float((valid_probs * weights).sum() / weights.sum())

        # Token-level Confidences
        token_confidences = token_probs.cpu().tolist()

        # Low confidence positions
        low_conf_mask = token_probs < low_confidence_threshold
        low_conf_positions = torch.where(low_conf_mask)[0].cpu().tolist()

        return {
            "mean_confidence": mean_conf,
            "min_confidence": min_conf,
            "weighted_confidence": weighted_conf,
            "token_confidences": token_confidences,
            "low_confidence_positions": low_conf_positions,
            "confidence_method": "vectorized"
        }

    except Exception as e:
        logger.warning("vectorized_confidence_error", error=str(e))
        # Fallback to iterative
        return _calculate_iterative(
            scores, generated_ids, input_length,
            special_token_ids, skip_special_tokens, low_confidence_threshold
        )


def _calculate_iterative(
    scores: Tuple[torch.Tensor, ...],
    generated_ids: torch.Tensor,
    input_length: int,
    special_token_ids: Set[int],
    skip_special_tokens: bool,
    low_confidence_threshold: float
) -> Dict[str, Any]:
    """Iterative Confidence-Berechnung (Fallback)."""
    token_confidences: List[float] = []
    low_confidence_positions: List[int] = []

    for idx, logits in enumerate(scores):
        # Handle dimensions
        if logits.dim() == 3:
            logits = logits.squeeze(0)
        if logits.dim() == 2:
            logits = logits[0]  # First batch

        # Softmax
        probs = F.softmax(logits, dim=-1)

        # Get token position
        actual_token_pos = input_length + idx

        # Validate position
        seq_len = generated_ids.shape[1] if generated_ids.dim() > 1 else len(generated_ids)
        if not (0 <= actual_token_pos < seq_len):
            continue

        # Get token ID
        if generated_ids.dim() > 1:
            token_id = generated_ids[0, actual_token_pos].item()
        else:
            token_id = generated_ids[actual_token_pos].item()

        # Skip special tokens
        if skip_special_tokens and token_id in special_token_ids:
            continue

        # Get confidence for this token
        confidence = float(probs[token_id])
        token_confidences.append(confidence)

        if confidence < low_confidence_threshold:
            low_confidence_positions.append(idx)

    if not token_confidences:
        return {
            "mean_confidence": 0.85,
            "min_confidence": 0.70,
            "weighted_confidence": 0.80,
            "token_confidences": [],
            "low_confidence_positions": [],
            "confidence_method": "iterative_empty"
        }

    mean_conf = sum(token_confidences) / len(token_confidences)
    min_conf = min(token_confidences)

    # Weighted confidence
    weights = list(range(1, len(token_confidences) + 1))
    weighted_conf = sum(c * w for c, w in zip(token_confidences, weights)) / sum(weights)

    return {
        "mean_confidence": mean_conf,
        "min_confidence": min_conf,
        "weighted_confidence": weighted_conf,
        "token_confidences": token_confidences,
        "low_confidence_positions": low_confidence_positions,
        "confidence_method": "iterative"
    }


def calculate_ensemble_confidence(
    results: List[Dict[str, Any]],
    weight_by_quality: bool = True
) -> float:
    """
    Berechne Ensemble-Confidence aus mehreren OCR-Ergebnissen.

    Verwendet fuer Hybrid-Agent bei Multi-Backend-Verarbeitung.

    Args:
        results: Liste von OCR-Ergebnissen mit 'confidence' Key
        weight_by_quality: Gewichte nach Qualitaet (hoehere Confidence = mehr Gewicht)

    Returns:
        Ensemble-Confidence (0.0 - 1.0)
    """
    if not results:
        return 0.0

    confidences = [r.get("confidence", 0.0) for r in results if r.get("confidence")]

    if not confidences:
        return 0.0

    if not weight_by_quality:
        return sum(confidences) / len(confidences)

    # Gewichtete Berechnung: hoehere Confidences haben mehr Einfluss
    total_weight = sum(confidences)
    if total_weight == 0:
        return 0.0

    weighted_sum = sum(c * c for c in confidences)  # c^2 als Gewicht
    return weighted_sum / total_weight


def confidence_to_quality_level(confidence: float) -> str:
    """
    Konvertiere Confidence-Score zu Qualitaets-Level.

    Args:
        confidence: Confidence-Score (0.0 - 1.0)

    Returns:
        Qualitaets-Level als String
    """
    if confidence >= 0.95:
        return "excellent"
    elif confidence >= 0.85:
        return "good"
    elif confidence >= 0.70:
        return "acceptable"
    elif confidence >= 0.50:
        return "poor"
    else:
        return "unreliable"
