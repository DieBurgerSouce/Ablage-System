# Plan: Vollstaendige Dokumenten-Vektorisierungs-Pipeline

## Zusammenfassung

**Ziel**: Enterprise-Dokumentenverarbeitung mit:
1. OCR-Textextraktion (bereits vorhanden)
2. Umlaut-Korrektur und Textbereinigung (bereits vorhanden, optimieren)
3. Automatische Uebersetzung (Russisch/Englisch -> Deutsch)
4. LLM-basierte strukturierte Datenextraktion (Rechnungen, Bestellungen, Vertraege)
5. Vektorisierung fuer semantische Suche (bereits vorhanden)

**Lokale Modelle (0 API-Kosten)**:
- `Qwen2.5-VL-7B-Instruct` - Strukturierte JSON-Extraktion (14GB VRAM)
- `DeepSeek-Janus-Pro-7B` - Komplexe Layouts/Tabellen (12-24GB VRAM)
- `multilingual-e5-large` - Embeddings (bereits aktiv)

---

## Architektur

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    DOKUMENT-PIPELINE (Erweitert)                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  1. UPLOAD & OCR                                                        │
│     PDF/TIF/Bild -> Surya/DeepSeek OCR -> Rohtext                      │
│                                                                         │
│  2. SPRACHERKENNUNG & UEBERSETZUNG (NEU)                               │
│     Rohtext -> Lingua/Langdetect -> Sprache                            │
│     Wenn nicht Deutsch: -> MarianMT/NLLB -> Deutscher Text             │
│     Original + Uebersetzung speichern                                  │
│                                                                         │
│  3. UMLAUT-KORREKTUR (Optimiert)                                       │
│     Deutscher Text -> GermanCorrectionAgent -> Sauberer Text           │
│     11-Stufen-Pipeline (bereits vorhanden)                             │
│                                                                         │
│  4. STRUKTURIERTE EXTRAKTION (NEU)                                     │
│     Sauberer Text + Bild -> Qwen2.5-VL -> Strukturierte Daten (JSON)   │
│     ├─ Dokumenttyp (Rechnung/Bestellung/Vertrag/Brief/Sonstiges)       │
│     ├─ Absender (Firma, Person, Adresse, IBAN, USt-ID)                │
│     ├─ Empfaenger (Firma, Person, Adresse, IBAN)                      │
│     ├─ Positionen (Artikel, Menge, Einzelpreis, Gesamtpreis)          │
│     ├─ Betraege (Netto, MwSt, Brutto, Waehrung)                       │
│     ├─ Daten (Rechnungsdatum, Faelligkeit, Liefertermin)              │
│     └─ Referenzen (Rechnungsnr, Bestellnr, Vertragsnr)                │
│                                                                         │
│  5. VEKTORISIERUNG (Bereits vorhanden)                                 │
│     Sauberer Text -> multilingual-e5-large -> 1024-dim Vektor         │
│     -> PostgreSQL pgvector (HNSW Index)                                │
│                                                                         │
│  6. SPEICHERUNG                                                         │
│     documents.extracted_text      = Sauberer Text                      │
│     documents.extracted_text_orig = Original (wenn uebersetzt)         │
│     documents.extracted_data      = JSON (strukturierte Daten)         │
│     documents.embedding           = Vektor (1024 dim)                  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Zu erstellende Dateien

| Datei | Zweck |
|-------|-------|
| `app/services/translation_service.py` | Automatische Uebersetzung mit MarianMT/NLLB |
| `app/services/structured_extraction_service.py` | LLM-basierte JSON-Extraktion |
| `app/agents/postprocessing/structured_extraction_agent.py` | Qwen2.5-VL Agent fuer Extraktion |
| `app/db/models/extracted_data.py` | Pydantic-Modelle fuer strukturierte Daten |
| `alembic/versions/xxx_add_extraction_fields.py` | DB-Migration fuer neue Felder |
| `tests/unit/services/test_translation_service.py` | Unit-Tests |
| `tests/unit/services/test_structured_extraction.py` | Unit-Tests |

---

## Zu modifizierende Dateien

| Datei | Aenderungen |
|-------|-------------|
| `app/db/models.py` | Neue Felder: `extracted_text_original`, `source_language`, `extracted_data` |
| `app/services/ocr_pipeline.py` | Uebersetzungs-Schritt einbauen |
| `app/workers/tasks/ocr_tasks.py` | Strukturierte Extraktion nach OCR |
| `app/core/config.py` | Konfiguration fuer Translation + Extraction |
| `requirements.txt` | `transformers`, `sentencepiece` fuer MarianMT |

---

## Implementierungsschritte

### Schritt 1: Datenmodelle fuer strukturierte Extraktion

**Datei**: `app/db/models/extracted_data.py`

```python
from pydantic import BaseModel
from typing import List, Optional
from datetime import date
from decimal import Decimal

class Address(BaseModel):
    company: Optional[str] = None
    person: Optional[str] = None
    street: Optional[str] = None
    zip_code: Optional[str] = None
    city: Optional[str] = None
    country: str = "DE"

class BankAccount(BaseModel):
    iban: Optional[str] = None
    bic: Optional[str] = None
    bank_name: Optional[str] = None

class LineItem(BaseModel):
    position: int
    description: str
    quantity: Optional[Decimal] = None
    unit: Optional[str] = None
    unit_price: Optional[Decimal] = None
    total_price: Optional[Decimal] = None
    vat_rate: Optional[Decimal] = None

class ExtractedDocument(BaseModel):
    document_type: str  # invoice, order, contract, letter, other

    # Absender
    sender: Address
    sender_bank: Optional[BankAccount] = None
    sender_vat_id: Optional[str] = None

    # Empfaenger
    recipient: Address
    recipient_bank: Optional[BankAccount] = None

    # Referenzen
    document_number: Optional[str] = None  # Rechnungs-/Bestellnummer
    reference_number: Optional[str] = None  # Kundennummer, Auftragsnummer

    # Daten
    document_date: Optional[date] = None
    due_date: Optional[date] = None
    delivery_date: Optional[date] = None

    # Positionen (bei Rechnungen/Bestellungen)
    line_items: List[LineItem] = []

    # Betraege
    net_amount: Optional[Decimal] = None
    vat_amount: Optional[Decimal] = None
    gross_amount: Optional[Decimal] = None
    currency: str = "EUR"

    # Qualitaetsindikatoren
    extraction_confidence: float = 0.0
    fields_extracted: int = 0
    fields_total: int = 0
```

### Schritt 2: Uebersetzungs-Service

**Datei**: `app/services/translation_service.py`

Features:
- Modell: `Helsinki-NLP/opus-mt-{src}-de` (MarianMT) oder `facebook/nllb-200-distilled-600M`
- Unterstuetzte Sprachen: RU, EN, PL, UK, FR, ES, IT -> DE
- Lazy Loading (Modell nur bei Bedarf laden)
- GPU-beschleunigt wenn verfuegbar
- Caching fuer wiederholte Uebersetzungen

```python
TRANSLATION_MODELS = {
    "ru": "Helsinki-NLP/opus-mt-ru-de",  # Russisch -> Deutsch
    "en": "Helsinki-NLP/opus-mt-en-de",  # Englisch -> Deutsch
    "pl": "Helsinki-NLP/opus-mt-pl-de",  # Polnisch -> Deutsch
    "uk": "Helsinki-NLP/opus-mt-uk-de",  # Ukrainisch -> Deutsch
    "fr": "Helsinki-NLP/opus-mt-fr-de",  # Franzoesisch -> Deutsch
}
```

Integration in Pipeline:
1. Spracherkennung (Lingua/Langdetect - bereits vorhanden)
2. Wenn Sprache != "de": Uebersetzung ausfuehren
3. Original-Text in `extracted_text_original` speichern
4. Uebersetzten Text in `extracted_text` speichern
5. `source_language` Feld setzen

### Schritt 3: Strukturierte Extraktions-Agent

**Datei**: `app/agents/postprocessing/structured_extraction_agent.py`

Verwendet Qwen2.5-VL-7B mit speziellem Prompt:

```python
EXTRACTION_PROMPT = """Analysiere dieses deutsche Geschaeftsdokument und extrahiere alle strukturierten Daten.

Gib die Daten als JSON zurueck mit folgender Struktur:
{
  "document_type": "invoice|order|contract|letter|other",
  "sender": {
    "company": "Firmenname",
    "person": "Ansprechpartner",
    "street": "Strasse und Hausnummer",
    "zip_code": "PLZ",
    "city": "Ort",
    "country": "DE"
  },
  "sender_bank": {
    "iban": "DE...",
    "bic": "...",
    "bank_name": "..."
  },
  "sender_vat_id": "DE...",
  "recipient": { ... },
  "document_number": "RE-2024-001",
  "document_date": "2024-01-15",
  "due_date": "2024-02-15",
  "line_items": [
    {
      "position": 1,
      "description": "Produktbeschreibung",
      "quantity": 10,
      "unit": "Stueck",
      "unit_price": 25.00,
      "total_price": 250.00,
      "vat_rate": 19
    }
  ],
  "net_amount": 250.00,
  "vat_amount": 47.50,
  "gross_amount": 297.50,
  "currency": "EUR"
}

Wichtig:
- Extrahiere NUR Felder die im Dokument sichtbar sind
- Alle Betraege als Dezimalzahlen (nicht als String)
- Daten im Format YYYY-MM-DD
- IBAN immer ohne Leerzeichen
- Bei Unsicherheit: null statt geraten
"""
```

### Schritt 4: Pipeline-Integration

**Datei**: `app/services/ocr_pipeline.py` (erweitern)

Neue Stages hinzufuegen:

```python
# Nach OCR und vor Embedding:
async def _translation_stage(self, result: Dict, options: Dict) -> Dict:
    """Uebersetze nicht-deutsche Texte."""
    if result.get("detected_language") != "de":
        original_text = result["text"]
        translated = await self.translation_service.translate(
            text=original_text,
            source_lang=result["detected_language"],
            target_lang="de"
        )
        result["text"] = translated
        result["text_original"] = original_text
        result["was_translated"] = True
    return result

async def _extraction_stage(self, result: Dict, image_path: str) -> Dict:
    """Extrahiere strukturierte Daten mit LLM."""
    extracted = await self.extraction_agent.process({
        "text": result["text"],
        "image_path": image_path,
    })
    result["extracted_data"] = extracted.get("data")
    result["extraction_confidence"] = extracted.get("confidence", 0.0)
    return result
```

### Schritt 5: Datenbank-Migration

**Datei**: `alembic/versions/xxx_add_extraction_fields.py`

```python
def upgrade():
    # Neue Spalten fuer Documents-Tabelle
    op.add_column('documents', sa.Column('extracted_text_original', sa.Text(), nullable=True))
    op.add_column('documents', sa.Column('source_language', sa.String(10), nullable=True))
    op.add_column('documents', sa.Column('extracted_data', JSONB(), nullable=True))
    op.add_column('documents', sa.Column('extraction_confidence', sa.Float(), nullable=True))
    op.add_column('documents', sa.Column('was_translated', sa.Boolean(), default=False))

    # Index fuer strukturierte Suche
    op.create_index('ix_documents_document_type', 'documents',
                    [sa.text("(extracted_data->>'document_type')")])
    op.create_index('ix_documents_sender_company', 'documents',
                    [sa.text("(extracted_data->'sender'->>'company')")])
```

### Schritt 6: Konfiguration

**Datei**: `app/core/config.py` (erweitern)

```python
# Translation Settings
TRANSLATION_ENABLED: bool = True
TRANSLATION_MODEL_TYPE: str = "marian"  # oder "nllb"
TRANSLATION_CACHE_ENABLED: bool = True
TRANSLATION_CACHE_TTL: int = 86400  # 24h

# Structured Extraction Settings
EXTRACTION_ENABLED: bool = True
EXTRACTION_MODEL: str = "qwen"  # oder "deepseek"
EXTRACTION_CONFIDENCE_THRESHOLD: float = 0.7
EXTRACTION_RETRY_ON_LOW_CONFIDENCE: bool = True
```

---

## Extrahierte Felder (Vollstaendig)

### Rechnungen (invoices)
| Feld | Beschreibung | Pflicht |
|------|--------------|---------|
| sender.company | Lieferant/Rechnungssteller | Ja |
| sender.street/zip/city | Adresse | Ja |
| sender_bank.iban | IBAN des Lieferanten | Ja |
| sender_vat_id | USt-IdNr. | Empfohlen |
| recipient.company | Kunde/Rechnungsempfaenger | Ja |
| document_number | Rechnungsnummer | Ja |
| document_date | Rechnungsdatum | Ja |
| due_date | Faelligkeitsdatum | Empfohlen |
| line_items[] | Positionen mit Preisen | Ja |
| net_amount | Nettobetrag | Ja |
| vat_amount | MwSt-Betrag | Ja |
| gross_amount | Bruttobetrag | Ja |

### Bestellungen (orders)
| Feld | Beschreibung | Pflicht |
|------|--------------|---------|
| sender.company | Besteller (wir) | Ja |
| recipient.company | Lieferant | Ja |
| document_number | Bestellnummer | Ja |
| document_date | Bestelldatum | Ja |
| delivery_date | Gewuenschter Liefertermin | Empfohlen |
| line_items[] | Bestellte Artikel | Ja |

### Vertraege (contracts)
| Feld | Beschreibung | Pflicht |
|------|--------------|---------|
| sender.company | Vertragspartner 1 | Ja |
| recipient.company | Vertragspartner 2 | Ja |
| document_number | Vertragsnummer | Empfohlen |
| document_date | Vertragsdatum | Ja |
| due_date | Vertragsende/Kuendigungsfrist | Empfohlen |
| gross_amount | Vertragswert (wenn angegeben) | Optional |

---

## Performance-Erwartungen

| Operation | Zeit (pro Dokument) | VRAM |
|-----------|---------------------|------|
| OCR (Surya) | 10-15s | 0 GB |
| Spracherkennung | <100ms | 0 GB |
| Uebersetzung (MarianMT) | 1-2s | ~2 GB |
| Umlaut-Korrektur | <500ms | 0 GB |
| Strukturierte Extraktion (Qwen) | 5-10s | 14 GB |
| Embedding | 200ms | 2 GB |
| **Gesamt** | 20-30s | Max 14 GB |

---

## Kritische Dateien (Referenz)

| Zweck | Datei |
|-------|-------|
| OCR Pipeline | `app/services/ocr_pipeline.py` |
| OCR Service | `app/services/ocr_service.py` |
| Embedding Service | `app/services/embedding_service.py` |
| Spracherkennung | `app/agents/orchestration/language_detector.py` |
| German Correction | `app/agents/postprocessing/german_correction_agent.py` |
| Qwen Agent (Vorlage) | `app/agents/ocr/qwen_ocr_agent.py` |
| DB Models | `app/db/models.py` |
| Celery Tasks | `app/workers/tasks/ocr_tasks.py` |
| Config | `app/core/config.py` |

---

## Semantische Suche (Bereits vorhanden)

Nach vollstaendiger Verarbeitung koennen Dokumente durchsucht werden:

```sql
-- Beispiel: Alle Rechnungen von "Firma XYZ" mit Betrag > 1000 EUR
SELECT * FROM documents
WHERE extracted_data->>'document_type' = 'invoice'
  AND extracted_data->'sender'->>'company' ILIKE '%XYZ%'
  AND (extracted_data->>'gross_amount')::numeric > 1000;

-- Semantische Aehnlichkeit
SELECT *, embedding <=> query_embedding AS distance
FROM documents
WHERE embedding <=> query_embedding < 0.5
ORDER BY distance
LIMIT 10;
```

---

## Fallback-Strategie

1. **Uebersetzung fehlgeschlagen** -> Original-Text verwenden (Embedding ist multilingual)
2. **Strukturierte Extraktion fehlgeschlagen** -> Nur OCR-Text speichern, `extracted_data = null`
3. **Qwen VRAM nicht verfuegbar** -> DeepSeek mit Quantisierung verwenden
4. **Niedriger Extraction-Confidence** -> Dokument als "needs_review" markieren

---

## Naechste Schritte nach Implementierung

1. **Frontend**: Strukturierte Daten im Dokument-Viewer anzeigen
2. **API**: Filter-Endpoints fuer strukturierte Suche
3. **Export**: CSV/Excel-Export der extrahierten Daten
4. **Validierung**: Manuelle Korrektur-UI fuer falsche Extraktionen
5. **Training**: Fine-Tuning von Qwen auf eigenen Dokumenten (optional)
