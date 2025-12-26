# PaddleOCR-VL 0.9B Evaluation - Quick Start Guide

**Status:** Phase 1-3 implementiert, bereit für Benchmark-Lauf

---

## Schnellstart

### 1. Voraussetzungen prüfen

```bash
# GPU verfügbar?
python -c "import torch; print('CUDA:', torch.cuda.is_available())"

# PaddleOCR-VL verfügbar? (kann fehlen, wird im Test geprüft)
python -c "from paddleocr_vl import PaddleOCRVL; print('Available')" || echo "Not available yet"
```

### 2. Basic Functionality Test (Go/No-Go)

```bash
# Test mit 3 Dokumenten
pytest tests/experimental/test_paddleocr_vl_basic.py -v -s --experimental -m gpu_required

# Oder manuell:
python scripts/test_paddleocr_vl_isolated.py
```

**Erwartetes Ergebnis:**
- ✅ Alle 3 Tests erfolgreich
- ✅ VRAM <14GB
- ✅ Umlaute erkannt
- ✅ Processing-Time <5s

### 3. Vollständiger Benchmark (wenn Basic Test GO)

```bash
# Benchmark auf 20 Dokumenten
python scripts/benchmark_paddleocr_vl.py --experimental

# Quick-Mode (nur 3 Dokumente)
python scripts/benchmark_paddleocr_vl.py --quick --experimental
```

### 4. Report generieren

```bash
python scripts/generate_paddleocr_vl_report.py
```

---

## Docker-Test (Isoliert)

```bash
# Container bauen
docker build -f docker/Dockerfile.paddleocr-vl-test -t paddleocr-vl-test .

# Test ausführen (mit GPU)
docker run --gpus all \
  -v "$(pwd)/tests/fixtures/german_docs:/app/test_images:ro" \
  -v "$(pwd)/data/benchmarks:/app/results" \
  paddleocr-vl-test
```

---

## Troubleshooting

### PaddleOCR-VL nicht verfügbar

**Problem:** `ImportError: PaddleOCR-VL nicht installiert`

**Lösung:**
```bash
# PaddleOCR-VL 0.9B ist möglicherweise noch nicht öffentlich verfügbar
# Fallback: Agent verwendet reguläres PaddleOCR für Tests
# Warten auf offizielle Veröffentlichung oder GitHub-Branch
```

### OOM-Fehler

**Problem:** `Out of Memory: VRAM exceeded`

**Lösung:**
- Batch-Size reduzieren
- Andere GPU-Prozesse beenden
- Fallback zu PP-OCRv5 (CPU)

### API-Unterschiede

**Problem:** API unterscheidet sich von erwartet

**Lösung:** Agent unterstützt mehrere API-Varianten automatisch

---

## Nächste Schritte nach Benchmark

### Bei GO-Entscheidung:
1. Phase 4.1: Agent-Refactoring
2. Phase 4.2: Router-Integration
3. Phase 4.3: Tests & Dokumentation

### Bei NO-GO-Entscheidung:
1. Ergebnisse dokumentieren
2. Alternative Strategien evaluieren
3. Warten auf optimierte Version

---

*Letzte Aktualisierung: 2025-12-20*

