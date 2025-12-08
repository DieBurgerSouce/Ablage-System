# OCR Backend Status Report

**Datum:** 2025-12-08
**Getestet auf:** RTX 4080 (16GB VRAM), Windows, CUDA 12.6

## Zusammenfassung

Von 11 implementierten OCR-Backends funktionieren **5 produktionsreif** auf dem aktuellen System.

**Empfehlung:** Surya als Standard-Backend, PaddleOCR für maximale Präzision.

## Manueller Genauigkeitstest (10 deutsche Geschäftsdokumente)

### Umlaut-Genauigkeit (ä, ö, ü, ß)

| Backend | Umlaut-Score | Beispiele |
|---------|--------------|-----------|
| **PaddleOCR** | **100%** | für ✅, fällig ✅, gemäß ✅, Gläubiger ✅ |
| **Surya** | **87.5%** | für ✅, fällig ✅, gemäß ✅ (nur "Gläubiger" fehlt) |
| **DocTR** | **0%** | fur ❌, fallig ❌, gemab ❌, Glaubiger ❌ |
| **GOT-OCR** | **50%** | Inkonsistent + Halluzinationen |

### Gesamtbewertung

| Backend | Umlaute | Speed | Stabilität | Empfehlung |
|---------|---------|-------|------------|------------|
| **Surya** | 87.5% | 44s | Sehr gut | **STANDARD - Beste Balance** |
| **PaddleOCR** | 100% | 13s | Gut (Docker) | **PRÄZISION - Wenn 100% nötig** |
| **DocTR** | 0% | 3s | Sehr gut | Nur für englische Dokumente |
| **GOT-OCR** | 50% | 352s | Schlecht | **NICHT VERWENDEN** |

## Funktionierende Backends (5)

| Backend | Typ | Zeit | Zeichen | Confidence | Empfehlung |
|---------|-----|------|---------|------------|------------|
| **Surya CPU** | CPU | ~44s | 1332 | 92% | **STANDARD - Beste Balance** |
| **Surya GPU** | GPU | ~14s | 1332 | 92% | GPU-beschleunigt |
| **PaddleOCR** | CPU (Docker) | ~13s | 1318 | 99% | **PRÄZISION - 100% Umlaute** |
| **DocTR** | CPU | ~3s | 1328 | 89% | Nur Englisch! |
| **GOT-OCR 2.0** | GPU | ~352s | 5178* | 71% | **NICHT EMPFOHLEN** |

*GOT-OCR: Zeichenzahl durch Halluzinationen aufgebläht (wiederholt Text hundertfach)

### Empfohlene Konfiguration

\`\`\`
Primary:     Surya CPU/GPU  (87.5% Umlaute, stabil, keine Dependencies)
Fallback:    PaddleOCR      (100% Umlaute, braucht Docker)
Schnell:     DocTR          (nur für englische Dokumente!)
VERMEIDEN:   GOT-OCR        (Halluzinationen, extrem langsam)
\`\`\`

## Detaillierte Testergebnisse

### Test-Setup
- 10 deutsche Geschäftsdokumente (Rechnungen, Lieferscheine)
- TIF-Format, 300 DPI
- Manueller Vergleich der OCR-Ausgabe mit Originaldokument

### Dokument 1: a.b.s. Rechenzentrum Rechnung

| Text im Original | DocTR | Surya | PaddleOCR | GOT-OCR |
|-----------------|-------|-------|-----------|---------|
| **für** | "fur" ❌ | "für" ✅ | "für" ✅ | "für" ✅ |
| **fällig** | "fallig" ❌ | "fällig" ✅ | "fällig" ✅ | "fallig" ❌ |
| **gemäß** | "gemab" ❌ | "gemäß" ✅ | "gemäß" ✅ | "gemäß" ✅ |
| **nächsten** | "nachsten" ❌ | "nächsten" ✅ | "nächsten" ✅ | "nächsten" ✅ |
| **Gläubiger** | "Glaubiger" ❌ | nicht erkannt | "Gläubiger" ✅ | "Glaubiger" ❌ |
| **sämtlicher** | "samtlicher" ❌ | "sämtlicher" ✅ | "sämtlicher" ✅ | "sammlicher" ❌ |
| IBAN | korrekt ✅ | korrekt ✅ | korrekt ✅ | Leerzeichen eingefügt |

### Dokument 2: GGS-Bestecke Rechnung

| Text im Original | PaddleOCR |
|-----------------|-----------|
| "Kochtöpfe" | "Kochtöpfe" ✅ |
| "zuzüglich" | "zuzüglich" ✅ |
| Handschrift "3400/72604" | "3400/72604" ✅ |
| IBAN | korrekt ✅ |

### GOT-OCR Probleme (KRITISCH)

GOT-OCR zeigt schwerwiegende Probleme:

1. **Halluzinationen:** Wiederholt Textfragmente hundertfach
   \`\`\`
   Ust-01/01
   Ust-01/01
   Ust-01/01
   ... (400+ Wiederholungen)
   \`\`\`

2. **Chat-Template-Artefakte:** Fügt System-Prompts ein
   \`\`\`
   system
   You should follow the instructions carefully...
   user
   OCR: assistant
   \`\`\`

3. **Extrem langsam:** 352 Sekunden (~6 Minuten) pro Dokument

**Fazit:** GOT-OCR ist für Produktion NICHT geeignet.

## Nicht-funktionierende Backends (6)

| Backend | Fehlertyp | Grund | Lösung |
|---------|-----------|-------|--------|
| **PaddleOCR (Windows)** | OneDNN Bug | Intel MKL Inkompatibilität | Docker verwenden |
| **DeepSeek-Janus** | Model Error | Braucht Janus-Library | Library installieren |
| **Chandra** | Zu langsam | VLM Token-für-Token | Nicht praktikabel |
| **Donut** | Dependency | sentencepiece Problem | Fix erforderlich |
| **Hybrid** | Abhängigkeit | Braucht funktionierendes Donut | Donut zuerst fixen |
| **Qwen-VL** | OOM | 7B braucht >16GB VRAM | 24GB+ GPU |
| **OlmOCR** | OOM | 7B Speicherproblem | 24GB+ GPU |

## Hardware-Anforderungen

| Backend | CPU RAM | GPU VRAM | Anmerkung |
|---------|---------|----------|-----------|
| DocTR | ~2GB | - | CPU only |
| Surya | ~4GB | ~4GB | CPU oder GPU |
| PaddleOCR | ~4GB | - | Docker erforderlich (Windows) |
| GOT-OCR | ~8GB | ~10GB | NICHT EMPFOHLEN |

## PaddleOCR Docker-Einrichtung

### Einzeldokument testen
\`\`\`bash
docker build -t paddleocr-test -f docker/Dockerfile.paddleocr-test .

docker run --rm \
  -v "C:/path/to/document.TIF:/app/test_images/document.TIF:ro" \
  -v "C:/path/to/results:/app/results" \
  paddleocr-test
\`\`\`

### Batch-Verarbeitung (10 Dokumente)
\`\`\`bash
docker build -t paddleocr-batch -f docker/Dockerfile.paddleocr-batch .

docker run --rm \
  -v "C:/path/to/tif_folder:/app/test_images:ro" \
  -v "C:/path/to/results:/app/results" \
  paddleocr-batch
\`\`\`

### PaddleOCR 3.x API-Hinweise
- Alte Parameter entfernt: \`use_gpu\`, \`show_log\`, \`use_angle_cls\`
- Neues Ergebnisformat: \`OCRResult.rec_texts\` und \`OCRResult.rec_scores\`
- Model-Cache: \`/root/.paddlex\` für persistenten Cache als Volume mounten

## Nächste Schritte

- [x] PaddleOCR in Docker testen - **99% Confidence, 100% Umlaute**
- [x] Manueller Genauigkeitsvergleich auf 10 Dokumenten
- [x] GOT-OCR Halluzinationsproblem dokumentiert
- [ ] Janus-Library für DeepSeek evaluieren
- [ ] 4-bit Quantisierung für VLMs testen

## Test-Skripte

- \`scripts/compare_ocr_detailed.py\` - Vergleich DocTR, Surya, GOT-OCR
- \`docker/Dockerfile.paddleocr-batch\` - PaddleOCR Batch-Verarbeitung
- \`docker/Dockerfile.paddleocr-test\` - PaddleOCR Einzeltest
