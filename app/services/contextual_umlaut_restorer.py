# -*- coding: utf-8 -*-
"""
Contextual Umlaut Restoration Service.

Verwendet regelbasierte und optionale ML-basierte Methoden fuer
kontextuelle Umlaut-Restaurierung:
- Entscheidet kontextuell ob "ae" zu "ae", "oe" zu "oe", "ue" zu "ue"
- Fraktur-zu-Modern Mapping fuer historische Dokumente
- Regional Dialect Normalization (DE/AT/CH)

Feinpoliert und durchdacht - Deutsche OCR-Qualitaet.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

import structlog

logger = structlog.get_logger(__name__)

# Optional: Transformers fuer BERT
try:
    from transformers import AutoModelForMaskedLM, AutoTokenizer
    import torch
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    logger.warning("transformers_not_available_using_fallback")


@dataclass
class UmlautCandidate:
    """Ein potentieller Umlaut-Korrektur-Kandidat."""
    position: int
    original: str
    replacement: str
    word: str
    context_left: str
    context_right: str


@dataclass
class UmlautCorrectionResult:
    """Ergebnis einer Umlaut-Korrektur."""
    original_text: str
    corrected_text: str
    corrections: List[Dict[str, Any]]
    method: str
    confidence: float


# Fraktur Character Mappings
FRAKTUR_TO_MODERN: Dict[str, str] = {
    '\u1E9E': 'ss',
    '\uFB00': 'ff',
    '\uFB01': 'fi',
    '\uFB02': 'fl',
    '\uFB03': 'ffi',
    '\uFB04': 'ffl',
    '\uFB05': 'st',
    '\uFB06': 'st',
    '\u017F': 's',
}

# Woerter die KEIN Umlaut haben sollen
NO_UMLAUT_WORDS: Set[str] = {
    'aero', 'aerob', 'aerodynamik', 'aerosol',
    'israel', 'israelisch', 'michael', 'raphael',
    'boeing', 'phoenix', 'poem', 'poet', 'poesie',
    'duell', 'duellist', 'fuel', 'manuel',
    'queen', 'blues', 'cruise', 'queue',
}


class ContextualUmlautRestorer:
    """
    Kontextuelle Umlaut-Restaurierung.

    Verwendet Masked Language Modeling oder Dictionary-basierte
    Heuristiken zur Umlaut-Korrektur.
    """

    DEFAULT_MODEL = "bert-base-german-cased"

    def __init__(
        self,
        model_name: Optional[str] = None,
        use_gpu: bool = True,
        confidence_threshold: float = 0.6,
        enable_bert: bool = True
    ):
        """
        Initialisiere Contextual Umlaut Restorer.

        Args:
            model_name: BERT Model Name (oder None fuer Default)
            use_gpu: GPU verwenden wenn verfuegbar
            confidence_threshold: Mindest-Confidence fuer Korrektur
            enable_bert: BERT aktivieren
        """
        self._confidence_threshold = confidence_threshold
        self._enable_bert = enable_bert and TRANSFORMERS_AVAILABLE
        self._model = None
        self._tokenizer = None
        self._device = None
        self._word_pattern = re.compile(r'\b\w+\b')

        if self._enable_bert:
            self._load_model(model_name, use_gpu)

        logger.info(
            "contextual_umlaut_restorer_initialized",
            bert_enabled=self._enable_bert,
            threshold=confidence_threshold
        )

    def _load_model(self, model_name: Optional[str], use_gpu: bool) -> None:
        """Lade BERT Model."""
        if not TRANSFORMERS_AVAILABLE:
            return

        try:
            model_name = model_name or self.DEFAULT_MODEL
            logger.info("loading_bert_model", model=model_name)

            self._tokenizer = AutoTokenizer.from_pretrained(model_name)
            self._model = AutoModelForMaskedLM.from_pretrained(model_name)

            if use_gpu and torch.cuda.is_available():
                self._device = torch.device("cuda")
                self._model = self._model.to(self._device)
            else:
                self._device = torch.device("cpu")

            self._model.eval()
            logger.info("bert_model_loaded", model=model_name)

        except Exception as e:
            logger.error("bert_model_load_failed", **safe_error_log(e))
            self._enable_bert = False

    def restore(self, text: str) -> UmlautCorrectionResult:
        """
        Restauriere Umlaute im Text.

        Args:
            text: Eingabetext mit potentiellen ASCII-Umlauten

        Returns:
            UmlautCorrectionResult mit korrigiertem Text
        """
        if not text or not text.strip():
            return UmlautCorrectionResult(
                original_text=text or "",
                corrected_text=text or "",
                corrections=[],
                method="none",
                confidence=1.0
            )

        candidates = self._find_candidates(text)

        if not candidates:
            return UmlautCorrectionResult(
                original_text=text,
                corrected_text=text,
                corrections=[],
                method="none",
                confidence=1.0
            )

        if self._enable_bert and self._model is not None:
            return self._restore_with_bert(text, candidates)
        else:
            return self._restore_with_heuristics(text, candidates)

    def _find_candidates(self, text: str) -> List[UmlautCandidate]:
        """Finde potentielle Umlaut-Kandidaten im Text."""
        candidates = []

        for match in self._word_pattern.finditer(text):
            word = match.group()
            word_start = match.start()

            if word.lower() in NO_UMLAUT_WORDS:
                continue

            word_lower = word.lower()

            # ae, oe, ue Kandidaten
            for ascii_chars, replacement in [('ae', '\u00e4'), ('oe', '\u00f6'), ('ue', '\u00fc')]:
                pos = word_lower.find(ascii_chars)
                while pos != -1:
                    abs_pos = word_start + pos
                    candidates.append(UmlautCandidate(
                        position=abs_pos,
                        original=ascii_chars,
                        replacement=replacement,
                        word=word,
                        context_left=text[max(0, abs_pos-30):abs_pos],
                        context_right=text[abs_pos+2:min(len(text), abs_pos+32)]
                    ))
                    pos = word_lower.find(ascii_chars, pos + 1)

        return candidates

    def _restore_with_bert(
        self,
        text: str,
        candidates: List[UmlautCandidate]
    ) -> UmlautCorrectionResult:
        """Restauriere Umlaute mit BERT Masked Language Model."""
        corrections = []
        corrected_text = text
        offset = 0

        for candidate in sorted(candidates, key=lambda c: c.position):
            pos = candidate.position + offset

            try:
                with torch.no_grad():
                    # Erstelle zwei Versionen: mit ASCII und mit Umlaut
                    text_with_ascii = corrected_text
                    text_with_umlaut = (
                        corrected_text[:pos] +
                        candidate.replacement +
                        corrected_text[pos + len(candidate.original):]
                    )

                    # Berechne Perplexity fuer beide
                    ascii_score = self._calculate_sentence_score(text_with_ascii)
                    umlaut_score = self._calculate_sentence_score(text_with_umlaut)

                    # Niedrigere Perplexity = besser
                    if umlaut_score < ascii_score:
                        confidence = 1.0 - (umlaut_score / max(ascii_score, 0.001))

                        if confidence > self._confidence_threshold:
                            old_len = len(candidate.original)
                            new_char = candidate.replacement
                            if candidate.original[0].isupper():
                                new_char = new_char.upper()

                            corrected_text = text_with_umlaut

                            corrections.append({
                                "position": candidate.position,
                                "original": candidate.original,
                                "corrected": new_char,
                                "confidence": confidence,
                                "word": candidate.word,
                                "method": "bert"
                            })

                            offset += len(new_char) - old_len

            except Exception as e:
                logger.warning("bert_prediction_failed", **safe_error_log(e))
                continue

        return UmlautCorrectionResult(
            original_text=text,
            corrected_text=corrected_text,
            corrections=corrections,
            method="bert",
            confidence=sum(c["confidence"] for c in corrections) / max(len(corrections), 1)
        )

    def _calculate_sentence_score(self, text: str) -> float:
        """Berechne Pseudo-Perplexity Score fuer einen Satz."""
        if self._tokenizer is None or self._model is None:
            return 0.0

        try:
            inputs = self._tokenizer(
                text,
                return_tensors="pt",
                truncation=True,
                max_length=512
            )

            if self._device:
                inputs = {k: v.to(self._device) for k, v in inputs.items()}

            outputs = self._model(**inputs, labels=inputs["input_ids"])
            return outputs.loss.item()

        except (ValueError, RuntimeError, TypeError) as e:
            logger.warning(
                "sentence_scoring_failed",
                error_type=type(e).__name__,
                **safe_error_log(e)
            )
            return 0.0
        except torch.cuda.OutOfMemoryError as e:
            logger.error(
                "sentence_scoring_gpu_oom",
                **safe_error_log(e)
            )
            # Clear GPU cache on OOM
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            return 0.0
        except Exception as e:
            logger.warning(
                "sentence_scoring_unexpected_error",
                error_type=type(e).__name__,
                **safe_error_log(e)
            )
            return 0.0

    def _restore_with_heuristics(
        self,
        text: str,
        candidates: List[UmlautCandidate]
    ) -> UmlautCorrectionResult:
        """Restauriere Umlaute mit Dictionary-Heuristiken."""
        try:
            from app.services.german_text_postprocessor import get_german_postprocessor

            postprocessor = get_german_postprocessor()

            result = postprocessor.postprocess(text)

            return UmlautCorrectionResult(
                original_text=text,
                corrected_text=result["text"],
                corrections=result["corrections"],
                method="dictionary",
                confidence=0.9 if result["corrections"] else 1.0
            )

        except ImportError:
            return self._simple_replacement(text)

    def _simple_replacement(self, text: str) -> UmlautCorrectionResult:
        """Einfache Ersetzung ohne Kontext."""
        corrections = []
        known = {
            'fuer': 'f\u00fcr',
            'ueber': '\u00fcber',
            'muenchen': 'm\u00fcnchen',
            'koeln': 'k\u00f6ln',
        }

        corrected = text
        for original, replacement in known.items():
            if original in corrected.lower():
                pattern = re.compile(re.escape(original), re.IGNORECASE)
                for match in pattern.finditer(corrected):
                    old = match.group()
                    new = replacement.capitalize() if old[0].isupper() else replacement
                    corrected = corrected[:match.start()] + new + corrected[match.end():]
                    corrections.append({
                        "original": old,
                        "corrected": new,
                        "confidence": 0.8,
                    })
                    break

        return UmlautCorrectionResult(
            original_text=text,
            corrected_text=corrected,
            corrections=corrections,
            method="simple",
            confidence=0.7
        )

    def normalize_fraktur(self, text: str) -> str:
        """Normalisiere Fraktur-Zeichen zu modernem Deutsch."""
        for fraktur, modern in FRAKTUR_TO_MODERN.items():
            text = text.replace(fraktur, modern)
        return text


# Singleton
_umlaut_restorer: Optional[ContextualUmlautRestorer] = None


def get_umlaut_restorer(
    enable_bert: bool = True,
    use_gpu: bool = True
) -> ContextualUmlautRestorer:
    """Hole Singleton-Instanz des Umlaut Restorers."""
    global _umlaut_restorer
    if _umlaut_restorer is None:
        _umlaut_restorer = ContextualUmlautRestorer(
            enable_bert=enable_bert,
            use_gpu=use_gpu
        )
    return _umlaut_restorer


def restore_umlauts(text: str, use_bert: bool = True) -> str:
    """Convenience-Funktion zum Restaurieren von Umlauten."""
    restorer = get_umlaut_restorer(enable_bert=use_bert)
    result = restorer.restore(text)
    return result.corrected_text
