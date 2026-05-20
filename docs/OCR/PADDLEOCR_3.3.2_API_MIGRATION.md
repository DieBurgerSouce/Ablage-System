# PaddleOCR 3.3.2 API Migration Guide

**Date:** 2025-12-19
**Version:** 3.3.2 (released 2025-11-13)

---

## Executive Summary

PaddleOCR 3.3.2 führt eine neue Pipeline-basierte API ein, die **nicht rückwärtskompatibel** mit der 2.x-Serie ist. Die Migration erfordert Anpassungen an Initialisierung und Verwendung.

---

## Breaking Changes

### Removed Parameters (2.x → 3.x)

| Parameter (2.x) | Status (3.x) | Alternative |
|----------------|--------------|-------------|
| `use_gpu` | ❌ Removed | Automatically detected or use device parameter |
| `show_log` | ❌ Removed | Use logging configuration |
| `use_angle_cls` | ❌ Removed | Integrated into pipeline |
| `lang` | ✅ Still available | Language parameter |

### New API Structure

PaddleOCR 3.x verwendet eine Pipeline-basierte Architektur:
- `_pipelines` Modul für Verarbeitung
- Automatische Geräteerkennung (CPU/GPU)
- Vereinfachte Initialisierung

---

## Migration Steps

### 1. Initialisierung (2.x → 3.x)

**Old (2.x):**
```python
from paddleocr import PaddleOCR

ocr = PaddleOCR(
    use_angle_cls=True,
    lang='german',
    use_gpu=False,
    show_log=False
)
```

**New (3.3.2):**
```python
from paddleocr import PaddleOCR

# Minimal initialization - parameters auto-detected
ocr = PaddleOCR(lang='german')

# Or with explicit device (if needed)
# Device is auto-detected, but can be specified via environment
```

### 2. OCR Processing

Die `.ocr()` Methode hat sich geändert:
```python
# Old (2.x):
result = ocr.ocr(image_path, cls=True)

# New (3.3.2):
result = ocr.ocr(image_path)  # cls parameter removed
# Returns: {'ocr_result': [[[bbox], (text, confidence)], ...], ...} or list format
```

**Wichtig:** Das Rückgabeformat ist jetzt ein Dictionary mit `'ocr_result'` Key, nicht mehr direkt eine Liste.

### 3. Language Support

Deutsche Sprache weiterhin unterstützt:
```python
ocr = PaddleOCR(lang='german')
```

---

## API Reference (3.3.2)

### PaddleOCR.__init__()

**Parameters:**
- `lang` (str, optional): Language code (default: 'ch' for Chinese)
- `det` (bool, optional): Enable text detection (default: True)
- `rec` (bool, optional): Enable text recognition (default: True)
- `cls` (bool, optional): Enable angle classification (default: False)
- `use_angle_cls` (bool, optional): **DEPRECATED** - Use `cls` instead
- `use_gpu` (bool, optional): **DEPRECATED** - Auto-detected
- `show_log` (bool, optional): **DEPRECATED** - Use logging

**Device Detection:**
- GPU wird automatisch erkannt, wenn verfügbar
- CPU wird als Fallback verwendet
- Keine explizite `use_gpu` Parameter mehr nötig

---

## Compatibility Notes

### PaddlePaddle Version

PaddleOCR 3.3.2 erfordert:
- PaddlePaddle >= 2.6.0 (CPU)
- PaddlePaddle-GPU >= 2.6.0 (GPU)

### NumPy Compatibility

⚠️ **Warning:** NumPy 2.x kann Kompatibilitätsprobleme verursachen
- Empfohlen: `numpy<2.0` für PyTorch-Kompatibilität
- PaddleOCR funktioniert mit NumPy 1.x und 2.x

---

## Testing Checklist

- [ ] Initialisierung mit `lang='german'` funktioniert
- [ ] OCR-Verarbeitung liefert korrekte Ergebnisse
- [ ] Deutsche Umlaute werden erkannt
- [ ] CPU-Modus funktioniert (wenn GPU nicht verfügbar)
- [ ] GPU-Modus funktioniert (wenn verfügbar)
- [ ] Rückgabeformat ist unverändert: `[[[bbox], (text, confidence)], ...]`

---

## References

- [PaddleOCR GitHub](https://github.com/PaddlePaddle/PaddleOCR)
- [PaddleOCR Documentation](https://www.paddleocr.ai/)
- [Upgrade Notes](https://paddlepaddle.github.io/PaddleOCR/main/en/update/upgrade_notes.html)

---

*Letzte Aktualisierung: 2025-12-19*

