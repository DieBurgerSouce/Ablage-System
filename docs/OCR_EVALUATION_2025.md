# OCR-Backend Evaluierung - Ablage-System

**Datum:** Dezember 2025
**Hardware:** NVIDIA RTX 4080 (16GB VRAM)
**Use-Case:** Deutsche Geschaftsdokumente (Rechnungen, IBAN/BIC-Erkennung)

---

## Executive Summary

Nach umfangreichen Tests mit 4 OCR-Backends und Recherche der aktuellen State-of-the-Art Modelle (Stand: Dezember 2025) ist **Surya GPU** die optimale Wahl fur unser System.

---

## 1. Durchgefuhrte Tests

### 1.1 Getestete Backends

| Backend | Modell | VRAM | GPU |
|---------|--------|------|-----|
| DeepSeek-Janus-Pro | deepseek-ai/Janus-Pro-1B | 12GB | Ja |
| GOT-OCR 2.0 | stepfun-ai/GOT-OCR-2.0-hf | 10GB | Ja |
| Surya GPU | VikParuchuri/surya | 2.5GB | Ja |
| Surya CPU | VikParuchuri/surya | 0GB | Nein |

### 1.2 Testergebnisse (10 deutsche Rechnungsdokumente)

| Backend | Zeit/Dok | Durchsatz | IBAN/BIC | Halluzinationen | Qualitat |
|---------|----------|-----------|----------|-----------------|----------|
| **Surya GPU** | 6-17s | 4-10 Dok/Min | Korrekt | Keine | Sehr gut |
| GOT-OCR 2.0 | 71s | 0.8 Dok/Min | Fehler | Ja | Mittel |
| DeepSeek-Janus | ~30s | 2 Dok/Min | Variabel | Ja | Variabel |

### 1.3 Kritische Qualitatsunterschiede

**Beispiel: Dokument 00000014.TIF (Rechnung mit IBAN)**

```
GOT-OCR 2.0:
  IBAN: DE7334270024001292100  (FALSCH - Ziffer fehlt)
  BIC:  BULTDE06342            (FALSCH - komplett falsch)

Surya GPU:
  IBAN: DE73342700240012922100 (KORREKT)
  BIC:  DEUTDEDB342            (KORREKT)
```

**GOT-OCR Probleme:**
- System-Prompt-Leakage im Output (`system\nuser\nassistant`)
- Null-Sequenz-Halluzinationen
- Worter ohne Leerzeichen zusammengezogen
- 10x langsamer bei 4x mehr VRAM-Verbrauch

**DeepSeek Probleme:**
- Erfindet Inhalte die nicht im Dokument stehen
- Unzuverlassige Ergebnisse bei wiederholter Verarbeitung

---

## 2. State-of-the-Art OCR (Dezember 2025)

### 2.1 Neue Open-Source Champions (Oktober 2025)

| Modell | Parameter | Benchmark | Besonderheit |
|--------|-----------|-----------|--------------|
| OlmOCR-2 | 7B | 82.4% olmOCR-Bench | SOTA, vollstandig offen |
| MiniCPM-o 2.6 | 8B | #1 OCRBench | Schlagt GPT-4o |
| Qwen2.5-VL | 7B-72B | ~75% JSON | GPT-4o Level |
| LightOnOCR-1B | 1B | SOTA/Grosse | 6x schneller als dots.ocr |
| Mistral OCR | - | 72.2% | 2000 Seiten/Min (API) |

### 2.2 Etablierte Performer

| Modell | Starken | VRAM |
|--------|---------|------|
| Surya | 97.7% auf Rechnungen, Layout-Analyse, 90+ Sprachen | 2.5GB |
| PaddleOCR PP-OCRv5 | 106 Sprachen, +13% vs v4 | ~2GB |
| DocTR | Deutsches Modell verfugbar | ~1GB |

### 2.3 Quellen

- [KDnuggets: 10 Awesome OCR Models 2025](https://www.kdnuggets.com/10-awesome-ocr-models-for-2025)
- [Modal: 8 Top Open-Source OCR Models](https://modal.com/blog/8-top-open-source-ocr-models-compared)
- [Researchify: OCR Comparison](https://researchify.io/blog/comparing-pytesseract-paddleocr-and-surya-ocr-performance-on-invoices)

---

## 3. Empfehlung

### 3.1 Kurzfristig: Surya GPU beibehalten

**Begrundung:**
- Beste IBAN/BIC-Genauigkeit in unseren Tests
- Keine Halluzinationen
- Ressourceneffizient (2.5GB von 16GB VRAM)
- 10x schneller als GOT-OCR
- Stabil und zuverlassig

**Keine Anderungen erforderlich.**

### 3.2 Mittelfristig: Qwen2.5-VL-7B evaluieren (optional)

**Warum interessant:**
- GPT-4o-Level Performance auf Benchmarks
- 7B Parameter = ~14GB VRAM (passt auf RTX 4080)
- Hervorragende Struktur-/JSON-Extraktion
- Native Multiresolution-Support

**Risiken:**
- Ungetestet mit deutschen IBAN/BIC
- Hoher VRAM-Verbrauch (14GB vs 2.5GB)
- Moglicherweise langsamer

---

## 4. Implementierungsplan (falls Qwen gewunscht)

### 4.1 Dateien

```
app/agents/ocr/qwen_ocr_agent.py    # Neu erstellen
app/gpu_manager.py                   # Backend hinzufugen
requirements.txt                     # transformers>=4.45 hinzufugen
```

### 4.2 Schritte

1. **Modell laden**
   ```python
   from transformers import Qwen2VLForConditionalGeneration
   model = Qwen2VLForConditionalGeneration.from_pretrained(
       "Qwen/Qwen2.5-VL-7B-Instruct",
       torch_dtype=torch.float16,
       device_map="cuda"
   )
   ```

2. **GPU-Allokation konfigurieren**
   - Backend: `qwen_ocr`
   - VRAM: 14GB
   - Prioritat: Nach Surya

3. **A/B-Test durchfuhren**
   - 100 Dokumente
   - Metriken: IBAN/BIC-Genauigkeit, Zeit, Umlaute

4. **Entscheidung treffen**
   - Bei >= Surya-Qualitat: Als Option anbieten
   - Bei < Surya-Qualitat: Verwerfen

---

## 5. Fazit

| Frage | Antwort |
|-------|---------|
| Ist Surya das beste Modell? | Fur unseren Use-Case: **Ja** |
| Gibt es bessere Benchmarks? | Ja (OlmOCR-2, Qwen2.5-VL) |
| Sollten wir wechseln? | **Nein** - Benchmarks != Praxis |
| Was ist der nachste Kandidat? | Qwen2.5-VL-7B (optional) |

**Surya GPU bleibt die empfohlene Wahl.**

Die neuen Oktober-2025-Modelle sind beeindruckend, aber:
1. Surya hat in UNSEREN Tests mit UNSEREN Dokumenten uberzeugt
2. IBAN/BIC-Genauigkeit ist kritisch - Surya liefert korrekt
3. Ressourceneffizienz (2.5GB vs 14GB) ist ein klarer Vorteil
4. "If it ain't broke, don't fix it"

---

## Anhang: Backend-Konfiguration

### Aktuelle OCR-Backends in `app/agents/ocr/`

| Datei | Status | Empfehlung |
|-------|--------|------------|
| `surya_gpu_agent.py` | Aktiv | **Primares Backend** |
| `surya_agent.py` | Aktiv | CPU-Fallback |
| `got_ocr_agent.py` | Aktiv | Nicht empfohlen |
| `deepseek_agent.py` | Aktiv | Nicht empfohlen |

### GPU-Allokation in `app/gpu_manager.py`

```python
BACKEND_VRAM = {
    "surya_gpu": 2.5,      # Empfohlen
    "got_ocr": 10.0,       # Nicht empfohlen
    "deepseek": 12.0,      # Nicht empfohlen
    # "qwen_ocr": 14.0,    # Optional hinzufugen
}
```
