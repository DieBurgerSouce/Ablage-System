# E-Invoice Implementierung (ZUGFeRD / XRechnung)

## Uebersicht

Das Ablage-System unterstuetzt die Verarbeitung elektronischer Rechnungen nach deutschen und europaeischen Standards:

- **ZUGFeRD 2.x** (Factur-X): PDF/A-3 mit eingebettetem XML fuer B2B
- **XRechnung 3.0.2**: XML-basiert fuer B2G (oeffentliche Auftraggeber)

## Architektur

```
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Backend                          │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐   │
│  │ Parser       │  │ Generator    │  │ Validator       │   │
│  │ Service      │  │ Service      │  │ Service         │   │
│  └──────┬───────┘  └──────┬───────┘  └────────┬────────┘   │
│         │                 │                    │            │
│         └────────┬────────┴────────────────────┘            │
│                  │                                          │
│         ┌────────┴────────┐                                 │
│         │                 │                                 │
│    ┌────▼────┐     ┌──────▼──────┐                         │
│    │factur-x │     │ Mustang     │                         │
│    │(Python) │     │ (Java/REST) │                         │
│    └─────────┘     └─────────────┘                         │
└─────────────────────────────────────────────────────────────┘
```

### Komponenten

| Komponente | Technologie | Verwendung |
|------------|-------------|------------|
| factur-x | Python | ZUGFeRD Lesen/Schreiben, CII-XML |
| Mustang | Java (Docker) | XRechnung UBL, KoSIT-Validierung |

## Installation

### 1. Python-Abhaengigkeiten

```bash
pip install factur-x lxml pikepdf
```

### 2. Mustang Microservice

Der Mustang-Service wird automatisch mit Docker Compose gestartet:

```bash
docker-compose up -d einvoice-mustang
```

Konfiguration in `docker-compose.yml`:
```yaml
einvoice-mustang:
  build:
    context: .
    dockerfile: docker/Dockerfile.mustang
  ports:
    - "127.0.0.1:8091:8091"
  environment:
    SERVER_PORT: 8091
    JAVA_OPTS: "-Xmx512m -Xms256m"
```

## API-Endpunkte

### Parsing

```http
POST /api/v1/einvoice/parse
Content-Type: multipart/form-data

file: <PDF oder XML Datei>
extract_to_document: true|false
```

Extrahiert E-Invoice-Daten aus ZUGFeRD-PDF oder XRechnung-XML.

### Generierung

#### ZUGFeRD PDF

```http
POST /api/v1/einvoice/generate/zugferd/{document_id}
Content-Type: application/json

{
  "profile": "EN16931"
}
```

Profile:
- `MINIMUM`: Minimale Rechnungsdaten
- `BASIC`: Basis-Rechnungsdaten
- `BASIC_WL`: Basic ohne Positionen
- `EN16931`: EU-Standard (empfohlen)
- `EXTENDED`: Erweiterte Daten
- `XRECHNUNG`: B2G-kompatibel

#### XRechnung XML

```http
POST /api/v1/einvoice/generate/xrechnung/{document_id}
Content-Type: application/json

{
  "syntax": "CII",
  "leitweg_id": "04011000-12345-67"
}
```

Syntaxen:
- `CII`: UN/CEFACT Cross Industry Invoice (empfohlen)
- `UBL`: Universal Business Language 2.1 (erfordert Mustang)

### Validierung

```http
POST /api/v1/einvoice/validate
Content-Type: multipart/form-data

file: <XML oder PDF Datei>
validator: AUTO|FACTURX|KOSIT|MUSTANG
```

Validatoren:
- `AUTO`: Automatische Auswahl
- `FACTURX`: Schnelle Python-Validierung
- `KOSIT`: Offizielle deutsche Validierung
- `MUSTANG`: Mustang-basierte Validierung

### Status abrufen

```http
GET /api/v1/einvoice/status/{document_id}
```

Response:
```json
{
  "has_einvoice": true,
  "document_id": "abc-123",
  "format": "zugferd",
  "profile": "EN16931",
  "version": "2.3.3",
  "is_valid": true,
  "leitweg_id": null,
  "validation_summary": {
    "error_count": 0,
    "warning_count": 2
  }
}
```

## Datenbank-Schema

### Tabelle: einvoice_documents

```sql
CREATE TABLE einvoice_documents (
    id UUID PRIMARY KEY,
    document_id UUID REFERENCES documents(id),
    format VARCHAR(50) NOT NULL,
    profile VARCHAR(50),
    version VARCHAR(20),
    xml_content TEXT,
    is_valid BOOLEAN,
    validation_errors JSONB,
    leitweg_id VARCHAR(100),
    was_generated BOOLEAN DEFAULT false,
    was_extracted BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_einvoice_leitweg ON einvoice_documents(leitweg_id);
CREATE INDEX idx_einvoice_document ON einvoice_documents(document_id);
```

## Frontend-Integration

### Komponenten

| Komponente | Beschreibung |
|------------|--------------|
| `EInvoiceStatusCard` | Status-Anzeige im Dokument |
| `EInvoiceGeneratorDialog` | ZUGFeRD/XRechnung-Generierung |
| `EInvoiceValidator` | Standalone-Validierung |
| `EInvoicePanel` | Tab im Document Viewer |

### Verwendung

```tsx
import {
  EInvoiceStatusCard,
  EInvoiceGeneratorDialog,
  useEInvoiceStatus
} from '@/features/einvoice';

function DocumentDetail({ documentId }: { documentId: string }) {
  const { data: status } = useEInvoiceStatus(documentId);
  const [generatorOpen, setGeneratorOpen] = useState(false);

  return (
    <>
      <EInvoiceStatusCard
        documentId={documentId}
        onGenerateClick={() => setGeneratorOpen(true)}
      />
      <EInvoiceGeneratorDialog
        documentId={documentId}
        open={generatorOpen}
        onOpenChange={setGeneratorOpen}
      />
    </>
  );
}
```

## Pflichtfelder

### ZUGFeRD EN16931

| Feld | BT-Nummer | Beschreibung |
|------|-----------|--------------|
| Rechnungsnummer | BT-1 | Eindeutige Nummer |
| Rechnungsdatum | BT-2 | Ausstellungsdatum |
| Rechnungstyp | BT-3 | 380 = Rechnung, 381 = Gutschrift |
| Waehrung | BT-5 | EUR, CHF, etc. |
| Verkaeufer | BT-27 | Name des Verkaeufers |
| Kaeufer | BT-44 | Name des Kaeufers |
| Gesamtbetrag | BT-112 | Brutto-Gesamtbetrag |

### XRechnung (zusaetzlich)

| Feld | BT-Nummer | Beschreibung |
|------|-----------|--------------|
| Leitweg-ID | BT-10 | **PFLICHT** fuer B2G |
| Verkaeufer-Adresse | BT-35-40 | Vollstaendige Adresse |
| E-Mail Verkaeufer | BT-34 | Elektronische Adresse |
| USt-IdNr. | BT-31 | Umsatzsteuer-ID |

## Fehlerbehandlung

### Haeufige Fehler

| Fehler | Ursache | Loesung |
|--------|---------|---------|
| `MISSING_LEITWEG_ID` | Leitweg-ID fehlt fuer XRechnung | Leitweg-ID im Dokument ergaenzen |
| `INVALID_PROFILE` | Ungültiges ZUGFeRD-Profil | Profil auf EN16931 aendern |
| `MUSTANG_UNAVAILABLE` | Mustang-Service nicht erreichbar | Service neu starten |
| `SCHEMA_VALIDATION_FAILED` | XML entspricht nicht Schema | Pflichtfelder pruefen |

### Logging

```python
import structlog
logger = structlog.get_logger(__name__)

logger.info(
    "einvoice_generated",
    document_id=doc_id,
    format="zugferd",
    profile="EN16931",
    processing_time_ms=elapsed
)
```

## Konfiguration

### Umgebungsvariablen

```env
# Mustang Service
MUSTANG_SERVICE_URL=http://einvoice-mustang:8091
MUSTANG_SERVICE_TIMEOUT=60

# E-Invoice Temp Directory
EINVOICE_TEMP_DIR=/app/temp/einvoice
```

### app/core/config.py

```python
class Settings(BaseSettings):
    # E-Invoice Settings
    MUSTANG_SERVICE_URL: str = "http://einvoice-mustang:8091"
    MUSTANG_SERVICE_TIMEOUT: int = 60
    EINVOICE_TEMP_DIR: Path = Path("/app/temp/einvoice")
```

## Weiterführende Links

- [ZUGFeRD Standard (FeRD)](https://www.ferd-net.de/)
- [XRechnung (XOeV)](https://www.xoev.de/xrechnung-16828)
- [E-Rechnungsportal Bund](https://www.e-rechnung-bund.de/)
- [KoSIT Validator](https://www.xoev.de/xrechnung/xrechnung_validierung-16832)
- [Mustang Project](https://github.com/ZUGFeRD/mustangproject)
