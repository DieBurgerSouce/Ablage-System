# OCR Backend Selection Guide

## Uebersicht

Das Ablage-System unterstuetzt mehrere OCR-Backends mit unterschiedlichen Staerken.
Dieses Guide hilft bei der Auswahl des optimalen Backends fuer verschiedene Anwendungsfaelle.

## Verfuegbare Backends

### 1. DeepSeek-Janus-Pro (GPU)

**Staerken:**
- Beste Umlaut-Genauigkeit (ä, ö, ü, ß)
- Exzellente Fraktur-Schrift-Erkennung
- Multimodale Vision-Language Faehigkeiten
- Komplexe Layout-Analyse

**Ressourcen:**
- VRAM: 12GB erforderlich
- GPU: NVIDIA RTX 3080/4080 oder besser

**Beste fuer:**
- Deutsche historische Dokumente
- Fraktur-Texte
- Dokumente mit komplexen Layouts
- Hoechste Qualitaetsanforderungen

**Konfiguration:**
```python
backend_config = {
    "name": "deepseek",
    "priority": 1,
    "max_batch_size": 4,
    "timeout_seconds": 300
}
```

### 2. GOT-OCR 2.0 (GPU)

**Staerken:**
- Schnelle Verarbeitung
- Gute Tabellen-Erkennung
- Formel-Support (LaTeX)
- Effiziente Batch-Verarbeitung

**Ressourcen:**
- VRAM: 10GB erforderlich
- GPU: NVIDIA RTX 3070 oder besser

**Beste fuer:**
- Schnelle Batch-Verarbeitung
- Tabellen-lastige Dokumente
- Wissenschaftliche Papers mit Formeln
- Standard-Business-Dokumente

**Konfiguration:**
```python
backend_config = {
    "name": "got_ocr",
    "priority": 2,
    "max_batch_size": 8,
    "timeout_seconds": 180
}
```

### 3. Surya + Docling (CPU/GPU)

**Staerken:**
- Beste Layout-Analyse
- Strukturierte Output-Formate
- Funktioniert ohne GPU
- Gute Dokumenten-Segmentierung

**Ressourcen:**
- VRAM: 4GB (optional, kann CPU nutzen)
- CPU: Moderne Multi-Core CPU

**Beste fuer:**
- Layout-Analyse
- Strukturierte Datenextraktion
- CPU-Only Deployments
- Dokumente mit vielen Bildern/Grafiken

**Konfiguration:**
```python
backend_config = {
    "name": "surya_docling",
    "priority": 3,
    "use_gpu": False,  # oder True
    "timeout_seconds": 240
}
```

### 4. Hybrid-Agent (Multi-Backend)

**Staerken:**
- Kombiniert mehrere Backends
- Automatische Qualitaetskontrolle
- Fallback bei Fehlern
- Ensemble-Confidence

**Beste fuer:**
- Hoechste Zuverlaessigkeit
- Kritische Dokumente
- Unbekannte Dokumenttypen
- Produktionsumgebungen

**Konfiguration:**
```python
hybrid_config = {
    "backends": ["deepseek", "got_ocr"],
    "voting_strategy": "confidence_weighted",
    "min_confidence": 0.8
}
```

## Auswahlkriterien

### Nach Dokumenttyp

| Dokumenttyp | Empfohlenes Backend |
|-------------|---------------------|
| Historische deutsche Dokumente | DeepSeek |
| Fraktur-Texte | DeepSeek |
| Rechnungen/Formulare | GOT-OCR |
| Wissenschaftliche Papers | GOT-OCR |
| Vertraege/Briefe | DeepSeek oder Hybrid |
| Tabellen-lastig | GOT-OCR |
| Komplexe Layouts | Surya + Docling |
| Unbekannt/Gemischt | Hybrid |

### Nach Ressourcen

| VRAM verfuegbar | Empfohlenes Backend |
|-----------------|---------------------|
| < 8GB | Surya (CPU) |
| 8-10GB | GOT-OCR |
| 10-12GB | DeepSeek oder GOT-OCR |
| > 12GB | DeepSeek oder Hybrid |

### Nach Prioritaet

| Prioritaet | Empfohlenes Backend |
|------------|---------------------|
| Qualitaet | DeepSeek oder Hybrid |
| Geschwindigkeit | GOT-OCR |
| Ressourcen-Effizienz | Surya |
| Zuverlaessigkeit | Hybrid |

## API-Verwendung

### Backend explizit waehlen

```bash
curl -X POST "http://localhost:8000/api/v1/ocr/process" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@document.pdf" \
  -F "backend=deepseek"
```

### Automatische Backend-Auswahl

```bash
curl -X POST "http://localhost:8000/api/v1/ocr/process" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@document.pdf" \
  -F "backend=auto"
```

### Hybrid-Verarbeitung

```bash
curl -X POST "http://localhost:8000/api/v1/ocr/process" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@document.pdf" \
  -F "backend=hybrid" \
  -F "hybrid_backends=deepseek,got_ocr"
```

## Confidence-Interpretation

| Confidence | Qualitaet | Empfehlung |
|------------|-----------|------------|
| > 0.95 | Exzellent | Direkt verwenden |
| 0.85 - 0.95 | Gut | Verwenden mit Stichproben |
| 0.70 - 0.85 | Akzeptabel | Manuelle Pruefung empfohlen |
| 0.50 - 0.70 | Schlecht | Alternatives Backend versuchen |
| < 0.50 | Unzuverlaessig | Manuelle Erfassung noetig |

## Troubleshooting

### Backend nicht verfuegbar

```bash
# Backend-Status pruefen
curl http://localhost:8000/api/v1/ocr/backends

# GPU-Status pruefen
nvidia-smi
```

### Niedrige Confidence

1. Bildqualitaet pruefen (min. 300 DPI)
2. Preprocessing aktivieren
3. Alternatives Backend testen
4. Hybrid-Modus verwenden

### VRAM-Probleme

1. Batch-Groesse reduzieren
2. Auf CPU-Backend wechseln
3. GPU-Cache leeren

```python
import torch
torch.cuda.empty_cache()
```

## Performance-Metriken

Durchschnittliche Verarbeitungszeit (A4, 300 DPI):

| Backend | Zeit/Seite | VRAM Peak |
|---------|------------|-----------|
| DeepSeek | 2-3s | 11GB |
| GOT-OCR | 0.8-1.5s | 8GB |
| Surya (GPU) | 1-2s | 4GB |
| Surya (CPU) | 3-5s | 0GB |
| Hybrid | 3-5s | 12GB |
