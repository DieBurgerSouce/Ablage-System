# OCR Backend Status Report

**Datum:** 2025-12-08
**Getestet auf:** RTX 4080 (16GB VRAM), Windows, CUDA 12.6

## Zusammenfassung

Von 11 implementierten OCR-Backends funktionieren **4 produktionsreif** auf dem aktuellen System.

## Funktionierende Backends (4)

| Backend | Typ | Zeit | Zeichen | Confidence | Empfehlung |
|---------|-----|------|---------|------------|------------|
| **DocTR** | CPU | ~3s | 1328 | 89% | Schnellstes CPU-Backend |
| **Surya CPU** | CPU | ~8s | 1332 | 92% | Beste Balance Qualitaet/Speed |
| **Surya GPU** | GPU | ~14s | 1332 | 92% | GPU-beschleunigt, gleiche Qualitaet |
| **GOT-OCR 2.0** | GPU | ~80s | 5178 | 71% | Maximale Vollstaendigkeit |

### Empfohlene Konfiguration

1. **Standard:** Surya CPU/GPU - Beste Balance aus Qualitaet (92%) und Geschwindigkeit
2. **High-Throughput:** DocTR - Schnellster Fallback
3. **Maximale Vollstaendigkeit:** GOT-OCR - 4x mehr extrahierte Zeichen

## Nicht-funktionierende Backends (7)

| Backend | Fehlertyp | Grund | Loesung |
|---------|-----------|-------|---------|
| **PaddleOCR** | OneDNN Bug | Intel MKL/MKLDNN Inkompatibilitaet auf Windows | Linux/Docker verwenden |
| **DeepSeek-Janus** | Model Error | Braucht spezielle Janus-Library | janus Library installieren |
| **Chandra** | Zu langsam | VLM generiert Token-fuer-Token (>7 Min/Bild) | Nicht praktikabel |
| **Donut** | Dependency | sentencepiece Tokenizer Problem | Dependency-Fix erforderlich |
| **Hybrid** | Abhaengigkeit | Braucht funktionierendes Donut | Donut zuerst fixen |
| **Qwen-VL** | OOM | 7B Modell braucht >16GB VRAM | 24GB+ GPU erforderlich |
| **OlmOCR** | OOM/Langsam | 7B Modell, Speicherproblem | 24GB+ GPU erforderlich |

## Technische Details

### Hardware-Anforderungen

- **DocTR:** CPU only, ~2GB RAM
- **Surya:** CPU: ~4GB RAM, GPU: ~4GB VRAM
- **GOT-OCR:** GPU: ~10GB VRAM
- **VLM-basiert (Chandra, Qwen, OlmOCR):** GPU: 20GB+ VRAM (nicht auf RTX 4080 moeglich)

### Bekannte Probleme

1. **PaddleOCR auf Windows:**
   ```
   NotFoundError: OneDnnContext does not have the input Filter
   ```
   - Intel MKL/OneDNN Inkompatibilitaet
   - Workaround: `enable_mkldnn=False` hilft nicht
   - Loesung: In Docker/Linux ausfuehren

2. **DeepSeek-Janus:**
   ```
   model type 'multi_modality' not recognized
   ```
   - Braucht spezielle Janus-Library von DeepSeek
   - Standard transformers unterstuetzt dieses Format nicht

3. **VLM Out-of-Memory:**
   - 7B Parameter Modelle brauchen ~15GB VRAM fuer Weights
   - Plus ~5-10GB fuer Inference
   - RTX 4080 hat nur 16GB

## Test-Skripte

- `scripts/test_all_backends.py` - Teste alle Backends via Agents
- `scripts/test_all_ocr_fixed.py` - Direkter API-Test mit Bugfixes
- `scripts/compare_ocr_content.py` - Inhaltlicher Vergleich

## Naechste Schritte

1. [ ] PaddleOCR in Docker testen
2. [ ] Janus-Library fuer DeepSeek evaluieren
3. [ ] 4-bit Quantisierung fuer VLMs auf Windows testen (bitsandbytes)
4. [ ] Donut sentencepiece Problem beheben
