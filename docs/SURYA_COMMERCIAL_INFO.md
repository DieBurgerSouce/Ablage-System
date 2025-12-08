# Surya OCR - Kommerzielle Lizenz-Analyse

**Stand:** 08. Dezember 2025
**Entwickler:** Datalab (VikParuchuri)
**Repository:** https://github.com/VikParuchuri/surya

---

## Ubersicht

Surya ist ein hochperformantes OCR-System mit GPU-Beschleunigung, entwickelt von Datalab. Es bietet exzellente Ergebnisse fur deutsche Dokumente, hat aber **komplexe Lizenzanforderungen** fur kommerzielle Nutzung.

---

## Technische Daten

| Eigenschaft | Wert |
|-------------|------|
| **VRAM** | 2.5GB (GPU) / 4GB (CPU) |
| **Sprachen** | 90+ (inkl. Deutsch) |
| **Benchmark** | 97.7% auf Rechnungen |
| **Architektur** | Pipeline (Detection + Recognition + Layout) |
| **Besonderheit** | Layout-Analyse, Tabellen-Erkennung |

---

## LIZENZSTRUKTUR - KRITISCH!

### Dual-Lizenz-System

Surya verwendet ein **Dual-Lizenz-Modell**:

```
┌─────────────────────────────────────────────────────────────┐
│                    SURYA LIZENZEN                           │
├─────────────────────────────────────────────────────────────┤
│  CODE (surya/*.py)          │  MODELL-WEIGHTS              │
│  ─────────────────          │  ─────────────────           │
│  GPL-3.0                    │  Custom License              │
│  (Copyleft)                 │  (cc-by-nc-sa-4.0 Basis)     │
└─────────────────────────────────────────────────────────────┘
```

### 1. Code-Lizenz: GPL-3.0

**Was GPL-3.0 bedeutet:**

```
GPL-3.0 = "Copyleft" Lizenz

Wenn du GPL-3.0 Code in deine Software einbaust:
  → Deine GESAMTE Software muss unter GPL-3.0 veroffentlicht werden
  → Du MUSST den Quellcode offentlich zuganglich machen
  → Jeder darf deine Software kopieren, modifizieren, weiterverkaufen
```

**Konkret fur dein Projekt:**

| Szenario | GPL-3.0 Konsequenz |
|----------|-------------------|
| Software intern nutzen | OK - keine Verteilung |
| Software als SaaS anbieten | OK - keine Verteilung des Codes |
| Software an Kunden verkaufen/geben | PROBLEM - Code muss offen sein |
| Software auf Kundenrechner installieren | PROBLEM - Code muss offen sein |

### 2. Modell-Weights Lizenz: Custom (cc-by-nc-sa-4.0 basiert)

**Aus der LICENSE Datei:**

```
The model weights are licensed under cc-by-nc-sa-4.0, with the
following exceptions:
- Researcher Exception: Free for academic/research use
- Startup Exception: Free for startups with < $2M revenue/funding
- Commercial License: Required for others
```

**Bedeutung:**

| Deine Situation | Weights-Lizenz |
|-----------------|----------------|
| Forschung/Akademisch | Kostenlos |
| Startup < $2M Umsatz/Funding | Kostenlos |
| Startup >= $2M oder etabliertes Unternehmen | Kommerzielle Lizenz erforderlich |

---

## LOSUNGSWEGE FUR KOMMERZIELLE NUTZUNG

### Option 1: Kommerzielle Lizenz von Datalab kaufen

**Kontakt:**
- Website: https://www.datalab.to/
- E-Mail: contact@datalab.to (vermutlich)
- Anfrage: "Commercial License for Surya OCR"

**Erwartete Kosten:**
- Keine offentlichen Preise verfugbar
- Typischerweise basiert auf:
  - Unternehmensgrose
  - Jahresumsatz
  - Anzahl Verarbeitungen/Monat
  - Support-Level

**Was du bekommst:**
- Recht zur Verteilung ohne GPL-Offenlegung
- Recht zur kommerziellen Nutzung der Weights
- Moglicherweise Support

**Anfrage-Template:**

```
Betreff: Commercial License Inquiry - Surya OCR

Sehr geehrtes Datalab-Team,

ich entwickle eine kommerzielle Dokumentenverarbeitungs-Software
und mochte Surya OCR integrieren.

Bitte teilen Sie mir die Konditionen fur eine kommerzielle Lizenz mit:

- Unternehmen: [Name]
- Branche: Dokumenten-Digitalisierung
- Erwartete Verarbeitung: [X] Dokumente/Monat
- Verteilungsmodell: On-Premises Software

Mit freundlichen Grussen,
[Name]
```

### Option 2: SaaS-Modell (GPL-Loophole)

**Konzept:** GPL-3.0 gilt nur bei **Verteilung** von Software. Wenn du die Software als Service anbietest, verteilst du keinen Code.

```
┌─────────────────────────────────────────────────────────────┐
│                    SAAS ARCHITEKTUR                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [Kunde] ──HTTP──> [Dein Server] ──> [Surya OCR]           │
│                         │                                   │
│                    (keine Code-Verteilung)                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Vorteile:**
- GPL-3.0 Code-Anforderung entfallt
- Kein Quellcode-Offenlegung notig

**Nachteile:**
- Modell-Weights-Lizenz gilt trotzdem!
- Startup-Exception nur bis $2M
- Kunde muss Internet-Verbindung haben

**WICHTIG:** Du brauchst trotzdem eine kommerzielle Lizenz fur die Weights, wenn du uber $2M Umsatz/Funding hast!

### Option 3: Surya komplett ersetzen

**Empfohlene Alternativen (Apache 2.0):**

| Alternative | Vergleich zu Surya |
|-------------|-------------------|
| **docTR** | Deutsches Modell, CPU-optimiert, etwas weniger genau |
| **OlmOCR-2** | Hohere Benchmark-Scores, mehr VRAM (14GB) |
| **Docling** | Layout-Analyse wie Surya, MIT-Lizenz |

**Migration von Surya zu docTR:**

```python
# VORHER (Surya)
from surya.ocr import run_ocr
from surya.model.detection import load_model as load_det_model
from surya.model.recognition import load_model as load_rec_model

det_model = load_det_model()
rec_model = load_rec_model()
result = run_ocr([image], [det_model, rec_model], ["de"])

# NACHHER (docTR)
from doctr.io import DocumentFile
from doctr.models import ocr_predictor

model = ocr_predictor(det_arch='db_resnet50', reco_arch='crnn_vgg16_bn', pretrained=True)
doc = DocumentFile.from_images([image_path])
result = model(doc)
text = result.export()
```

---

## UNSERE TESTERGEBNISSE

Aus `docs/OCR_EVALUATION_2025.md`:

| Metrik | Surya GPU | Vergleich |
|--------|-----------|-----------|
| **Zeit/Dokument** | 6-17s | 10x schneller als GOT-OCR |
| **IBAN-Erkennung** | Korrekt | GOT-OCR macht Fehler |
| **BIC-Erkennung** | Korrekt | GOT-OCR macht Fehler |
| **Halluzinationen** | Keine | DeepSeek erfindet Inhalte |
| **VRAM** | 2.5GB | Effizienteste Option |

**Beispiel IBAN-Vergleich (Dokument 00000014.TIF):**

```
Surya GPU:  DE73342700240012922100 (KORREKT)
GOT-OCR:    DE7334270024001292100  (FALSCH - Ziffer fehlt)
```

---

## ZUSAMMENFASSUNG

### Kann ich Surya kommerziell nutzen?

| Frage | Antwort |
|-------|---------|
| Intern nutzen? | JA (keine Verteilung) |
| Als SaaS anbieten? | JA, aber Weights-Lizenz beachten |
| Software verkaufen (< $2M)? | BEDINGT - nur mit SaaS oder Lizenz |
| Software verkaufen (>= $2M)? | NEIN ohne kommerzielle Lizenz |
| Code offenlegen? | Ja, wenn Software verteilt wird |

### Empfehlung

```
WENN du Software VERKAUFEN willst:
  → Kaufe kommerzielle Lizenz von Datalab
  ODER
  → Ersetze Surya durch docTR/Docling/OlmOCR-2

WENN du SaaS anbieten willst UND < $2M Umsatz:
  → Nutze Surya unter Startup-Exception
  → Plan fur Lizenz, wenn du wachst

WENN du nur intern nutzt:
  → Kein Problem, nutze Surya frei
```

---

## LINKS

- **GitHub:** https://github.com/VikParuchuri/surya
- **Datalab (Kommerziell):** https://www.datalab.to/
- **LICENSE:** https://github.com/VikParuchuri/surya/blob/master/LICENSE
- **Model LICENSE:** https://github.com/VikParuchuri/surya/blob/master/MODEL_LICENSE

---

## RISIKO-BEWERTUNG

| Risiko | Level | Beschreibung |
|--------|-------|--------------|
| GPL-Verletzung | HOCH | Bei Software-Verteilung ohne Quellcode-Offenlegung |
| Weight-Lizenz-Verletzung | MITTEL | Bei Uberschreitung der $2M-Grenze |
| Rechtliche Konsequenzen | HOCH | Abmahnung, Unterlassung, Schadensersatz |

**Meine Empfehlung fur dein Projekt:**

Fur ein kommerzielles Produkt, das du verkaufen mochtest:
1. **Kurzfristig:** Kontaktiere Datalab fur Lizenzkosten
2. **Langfristig:** Evaluiere docTR oder Docling als Drop-in-Ersatz
3. **Backup-Plan:** Halte Surya als interne Referenz, verkaufe mit Apache-2.0-Alternative
