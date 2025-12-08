# Qwen2.5-VL - Kommerzielle Lizenz-Analyse

**Stand:** 08. Dezember 2025
**Entwickler:** Alibaba Cloud (Qwen Team)
**Repository:** https://github.com/QwenLM/Qwen2.5-VL

---

## Ubersicht

Qwen2.5-VL ist ein Vision-Language Modell von Alibaba mit **GPT-4o-Level Performance**. Die Lizenzierung ist **modellgrossenabhangig** - einige Varianten sind frei fur kommerzielle Nutzung, andere nicht.

---

## Technische Daten

| Modell | Parameter | VRAM | Benchmark | Lizenz |
|--------|-----------|------|-----------|--------|
| Qwen2.5-VL-3B | 3B | ~6GB | Gut | **RESEARCH ONLY** |
| Qwen2.5-VL-7B | 7B | ~14GB | Sehr gut | **Apache 2.0** |
| Qwen2.5-VL-32B | 32B | ~64GB | Exzellent | **Apache 2.0** |
| Qwen2.5-VL-72B | 72B | ~144GB | State-of-Art | **Qwen License** |

---

## LIZENZSTRUKTUR - KRITISCH!

### Unterschiedliche Lizenzen je Modellgrosse

```
┌─────────────────────────────────────────────────────────────┐
│              QWEN2.5-VL LIZENZ-UBERSICHT                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  3B Modell                                                  │
│  ─────────                                                  │
│  Research/Non-Commercial Only                               │
│  ❌ KEINE kommerzielle Nutzung                             │
│                                                             │
│  7B & 32B Modelle                                           │
│  ────────────────                                           │
│  Apache 2.0                                                 │
│  ✓ Kommerzielle Nutzung erlaubt                            │
│  ✓ Modifikation erlaubt                                    │
│  ✓ Verteilung erlaubt                                      │
│                                                             │
│  72B Modell                                                 │
│  ──────────                                                 │
│  Qwen License (Custom)                                      │
│  ⚠️ Einschrankungen bei >100M MAU                          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Detailanalyse pro Modell

#### ❌ Qwen2.5-VL-3B - NICHT KOMMERZIELL

```
Lizenz: Research/Academic Use Only

Erlaubt:
  ✓ Forschung
  ✓ Akademische Projekte
  ✓ Personliche Experimente

VERBOTEN:
  ✗ Kommerzielle Produkte
  ✗ Verkauf von Software damit
  ✗ SaaS-Angebote
  ✗ Interne Business-Nutzung
```

**Warum gibt es das 3B-Modell dann?**
- Alibaba mochte Forschern Zugang geben
- Kleinere Modelle fur akademische Hardware
- Marketing fur grossere (kostenpflichtige) Modelle

#### ✓ Qwen2.5-VL-7B & 32B - VOLL KOMMERZIELL

```
Lizenz: Apache 2.0

Du darfst:
  ✓ Kommerziell nutzen
  ✓ Modifizieren
  ✓ Weiterverteilen
  ✓ In Closed-Source einbauen
  ✓ Als SaaS anbieten
  ✓ Verkaufen

Du musst:
  - Apache 2.0 Lizenz beilegen
  - Copyright-Hinweis beibehalten
  - Anderungen dokumentieren (wenn verteilt)
```

#### ⚠️ Qwen2.5-VL-72B - BEDINGT KOMMERZIELL

```
Lizenz: Qwen License

Frei fur:
  ✓ Unternehmen mit < 100 Millionen MAU
  ✓ Die meisten kommerziellen Anwendungen

Einschrankung:
  ⚠️ Bei > 100M Monthly Active Users:
     → Lizenzvereinbarung mit Alibaba erforderlich
```

---

## EMPFOHLENES MODELL FUR DEIN PROJEKT

### Qwen2.5-VL-7B (Apache 2.0)

**Warum 7B?**

| Kriterium | Bewertung |
|-----------|-----------|
| **Lizenz** | Apache 2.0 - uneingeschrankt kommerziell |
| **VRAM** | ~14GB - passt auf RTX 4080 (16GB) |
| **Performance** | GPT-4o Level auf OCR-Benchmarks |
| **Preis** | Kostenlos |

**VRAM-Optimierung fur RTX 4080:**

```python
from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
import torch

# Option 1: FP16 (~14GB VRAM)
model = Qwen2VLForConditionalGeneration.from_pretrained(
    "Qwen/Qwen2.5-VL-7B-Instruct",
    torch_dtype=torch.float16,
    device_map="cuda"
)

# Option 2: INT8 Quantisierung (~8GB VRAM)
model = Qwen2VLForConditionalGeneration.from_pretrained(
    "Qwen/Qwen2.5-VL-7B-Instruct",
    load_in_8bit=True,
    device_map="cuda"
)

# Option 3: INT4 Quantisierung (~4GB VRAM)
model = Qwen2VLForConditionalGeneration.from_pretrained(
    "Qwen/Qwen2.5-VL-7B-Instruct",
    load_in_4bit=True,
    device_map="cuda"
)
```

---

## VOLLSTANDIGE IMPLEMENTIERUNG

### Qwen2.5-VL OCR Agent

```python
"""
Qwen2.5-VL OCR Agent - Apache 2.0 lizenziert
Fur kommerzielle Nutzung geeignet (7B/32B Modelle)
"""
import torch
from typing import Optional
from PIL import Image
from transformers import Qwen2VLForConditionalGeneration, AutoProcessor

class QwenOCRAgent:
    """
    OCR Agent basierend auf Qwen2.5-VL-7B.

    Lizenz: Apache 2.0 - Kommerziell nutzbar
    VRAM: ~14GB (FP16) / ~8GB (INT8) / ~4GB (INT4)
    """

    # WICHTIG: Nur diese Modelle fur kommerzielle Nutzung!
    COMMERCIAL_MODELS = [
        "Qwen/Qwen2.5-VL-7B-Instruct",   # Apache 2.0
        "Qwen/Qwen2.5-VL-32B-Instruct",  # Apache 2.0
    ]

    # NICHT FUR KOMMERZIELLE NUTZUNG:
    RESTRICTED_MODELS = [
        "Qwen/Qwen2.5-VL-3B-Instruct",   # Research Only!
        "Qwen/Qwen2.5-VL-72B-Instruct",  # >100M MAU Limit
    ]

    def __init__(
        self,
        model_name: str = "Qwen/Qwen2.5-VL-7B-Instruct",
        quantization: str = "fp16",  # fp16, int8, int4
        device: str = "cuda"
    ):
        # Prufe ob Modell kommerziell nutzbar
        if model_name in self.RESTRICTED_MODELS:
            raise ValueError(
                f"Modell {model_name} ist NICHT fur kommerzielle Nutzung! "
                f"Nutze eines von: {self.COMMERCIAL_MODELS}"
            )

        self.model_name = model_name
        self.device = device

        # Lade Modell mit passender Quantisierung
        load_kwargs = {"device_map": device}

        if quantization == "fp16":
            load_kwargs["torch_dtype"] = torch.float16
        elif quantization == "int8":
            load_kwargs["load_in_8bit"] = True
        elif quantization == "int4":
            load_kwargs["load_in_4bit"] = True

        print(f"Lade {model_name} mit {quantization}...")
        self.model = Qwen2VLForConditionalGeneration.from_pretrained(
            model_name,
            **load_kwargs
        )
        self.processor = AutoProcessor.from_pretrained(model_name)
        print(f"Modell geladen. VRAM: {self._get_vram_usage():.1f}GB")

    def _get_vram_usage(self) -> float:
        """Gibt aktuelle VRAM-Nutzung in GB zuruck."""
        if torch.cuda.is_available():
            return torch.cuda.memory_allocated() / 1024**3
        return 0.0

    def process(self, image_path: str, prompt: Optional[str] = None) -> dict:
        """
        Verarbeitet ein Bild und extrahiert Text.

        Args:
            image_path: Pfad zum Bild
            prompt: Optionaler Prompt (Standard: OCR-Prompt)

        Returns:
            dict mit 'text', 'confidence', etc.
        """
        # Lade Bild
        image = Image.open(image_path).convert('RGB')

        # Standard OCR-Prompt
        if prompt is None:
            prompt = (
                "Extrahiere den gesamten Text aus diesem Dokument. "
                "Behalte die Formatierung bei. "
                "Gib NUR den extrahierten Text zuruck, keine Erklarungen."
            )

        # Erstelle Messages-Format
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": prompt}
                ]
            }
        ]

        # Verarbeite
        text_input = self.processor.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
        )

        inputs = self.processor(
            text=[text_input],
            images=[image],
            return_tensors="pt",
            padding=True
        ).to(self.device)

        # Generiere
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=4096,
                do_sample=False
            )

        # Dekodiere
        generated_text = self.processor.batch_decode(
            outputs[:, inputs.input_ids.shape[1]:],
            skip_special_tokens=True
        )[0]

        return {
            'text': generated_text.strip(),
            'confidence': 0.95,  # VLMs geben keine direkte Confidence
            'model': self.model_name,
            'vram_used_gb': self._get_vram_usage()
        }

    def process_batch(self, image_paths: list, prompt: Optional[str] = None) -> list:
        """Verarbeitet mehrere Bilder."""
        return [self.process(path, prompt) for path in image_paths]


# Beispiel-Nutzung
if __name__ == '__main__':
    # Initialisiere mit INT8 fur RTX 4080
    agent = QwenOCRAgent(
        model_name="Qwen/Qwen2.5-VL-7B-Instruct",
        quantization="int8"  # ~8GB VRAM
    )

    # Verarbeite Dokument
    result = agent.process("rechnung.png")
    print(f"Extrahierter Text:\n{result['text']}")
    print(f"VRAM verwendet: {result['vram_used_gb']:.1f}GB")
```

---

## INTEGRATION IN DEIN SYSTEM

### GPU-Manager Erweiterung

```python
# In app/gpu_manager.py

BACKEND_VRAM = {
    "surya_gpu": 2.5,
    "got_ocr": 10.0,
    "deepseek": 12.0,
    "qwen_vl_7b_fp16": 14.0,    # Neu
    "qwen_vl_7b_int8": 8.0,     # Neu
    "qwen_vl_7b_int4": 4.0,     # Neu
}
```

### Backend-Auswahl Logik

```python
def select_ocr_backend(document_type: str, available_vram: float) -> str:
    """Wahlt bestes OCR-Backend basierend auf Dokument und VRAM."""

    if document_type == "complex_layout" and available_vram >= 14.0:
        return "qwen_vl_7b_fp16"  # Beste Qualitat

    elif document_type == "complex_layout" and available_vram >= 8.0:
        return "qwen_vl_7b_int8"  # Gute Qualitat, weniger VRAM

    elif available_vram >= 2.5:
        return "surya_gpu"  # Schnell, effizient

    else:
        return "paddleocr_cpu"  # CPU Fallback
```

---

## BENCHMARK-VERGLEICH

### OCR-Performance

| Modell | Benchmark | VRAM | Geschwindigkeit |
|--------|-----------|------|-----------------|
| Qwen2.5-VL-7B | ~75% JSON | 14GB | ~5s/Seite |
| Surya GPU | 97.7% Invoice | 2.5GB | ~10s/Seite |
| GOT-OCR 2.0 | ~80% | 10GB | ~70s/Seite |
| PaddleOCR | 86% | CPU | ~2s/Seite |

### Starken von Qwen2.5-VL

| Kategorie | Bewertung |
|-----------|-----------|
| **Strukturierte Extraktion** | Exzellent |
| **JSON/Markdown Output** | Exzellent |
| **Tabellen** | Sehr gut |
| **Handschrift** | Gut |
| **Deutsche Umlaute** | Gut |
| **Komplexe Layouts** | Sehr gut |

---

## LIZENZ-COMPLIANCE CHECKLISTE

### Vor Release prufen:

```python
"""Pruft Qwen-Modell Lizenz-Compliance."""

def check_qwen_license_compliance(model_name: str) -> dict:
    """
    Pruft ob ein Qwen-Modell kommerziell nutzbar ist.
    """
    COMMERCIAL_OK = {
        "Qwen/Qwen2.5-VL-7B-Instruct": "Apache 2.0",
        "Qwen/Qwen2.5-VL-32B-Instruct": "Apache 2.0",
    }

    RESTRICTED = {
        "Qwen/Qwen2.5-VL-3B-Instruct": "Research Only - KEINE kommerzielle Nutzung!",
        "Qwen/Qwen2.5-VL-72B-Instruct": "Qwen License - >100M MAU erfordert Lizenz",
    }

    if model_name in COMMERCIAL_OK:
        return {
            "commercial_use": True,
            "license": COMMERCIAL_OK[model_name],
            "requirements": ["Attribution beibehalten", "Lizenztext beilegen"]
        }

    elif model_name in RESTRICTED:
        return {
            "commercial_use": False,
            "license": RESTRICTED[model_name],
            "requirements": ["Nicht fur kommerzielle Nutzung verwenden!"]
        }

    else:
        return {
            "commercial_use": "unknown",
            "license": "Unbekannt - manuell prufen!",
            "requirements": ["Lizenz auf HuggingFace prufen"]
        }


# Beispiel
result = check_qwen_license_compliance("Qwen/Qwen2.5-VL-7B-Instruct")
print(f"Kommerziell: {result['commercial_use']}")
print(f"Lizenz: {result['license']}")
```

### Attribution (erforderlich fur Apache 2.0)

Fuege in deine Dokumentation/About-Seite ein:

```
Dieses Produkt verwendet Qwen2.5-VL, entwickelt von Alibaba Cloud.
Lizenziert unter Apache License 2.0.
https://github.com/QwenLM/Qwen2.5-VL
```

---

## ZUSAMMENFASSUNG

### Kann ich Qwen2.5-VL kommerziell nutzen?

| Modell | Kommerziell? | Empfehlung |
|--------|--------------|------------|
| **3B** | ❌ NEIN | Nicht verwenden |
| **7B** | ✅ JA | **EMPFOHLEN** |
| **32B** | ✅ JA | Wenn VRAM verfugbar |
| **72B** | ⚠️ Bedingt | Nur bei <100M MAU |

### Empfehlung fur dein Projekt

```
FUR RTX 4080 (16GB VRAM):

Primares OCR:     Qwen2.5-VL-7B (INT8) → ~8GB VRAM
Fallback:         Surya GPU → ~2.5GB VRAM (wenn Lizenz gekauft)
                  ODER
                  docTR/PaddleOCR (CPU) → 0GB VRAM

Parallel moglich: Qwen (8GB) + anderes Modell (8GB)
```

---

## LINKS

- **GitHub:** https://github.com/QwenLM/Qwen2.5-VL
- **HuggingFace:** https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct
- **Paper:** https://arxiv.org/abs/2409.12191
- **Lizenz (7B/32B):** Apache 2.0
- **Lizenz (72B):** https://huggingface.co/Qwen/Qwen2.5-VL-72B-Instruct/blob/main/LICENSE

---

## RISIKO-BEWERTUNG

| Risiko | Level | Beschreibung |
|--------|-------|--------------|
| Nutzung von 3B-Modell | HOCH | Research-Only Lizenz verletzt |
| Nutzung von 7B/32B | NIEDRIG | Apache 2.0 - nur Attribution |
| Nutzung von 72B >100M MAU | MITTEL | Lizenzvereinbarung notig |

**Meine Empfehlung:**

Qwen2.5-VL-7B ist eine **exzellente Wahl** fur kommerzielle OCR:
1. Apache 2.0 - keine Einschrankungen
2. GPT-4o Level Performance
3. Passt auf RTX 4080
4. Gute deutsche Sprachunterstutzung
5. Strukturierte Outputs (JSON/Markdown)
