# Integration Guide

> **Ablage-System - Integrationsanleitung**
> Version: 1.0 | Stand: Januar 2025

---

## Übersicht

Dieses Dokument beschreibt die Integration externer Systeme mit dem Ablage-System:

1. [Authentifizierung](#authentifizierung)
2. [Webhooks](#webhooks)
3. [ERP-Integration](#erp-integration)
4. [DMS-Integration](#dms-integration)
5. [E-Mail-Integration](#e-mail-integration)
6. [Workflow-Automatisierung](#workflow-automatisierung)
7. [DATEV-Export](#datev-export)

---

## Authentifizierung

### JWT-Token-Authentifizierung

Das Ablage-System verwendet JWT-Tokens für die API-Authentifizierung.

```
┌─────────────┐      POST /auth/login       ┌─────────────────┐
│   Client    │ ──────────────────────────▶ │  Ablage-System  │
│             │ ◀────────────────────────── │                 │
└─────────────┘   {access_token, refresh}   └─────────────────┘
       │
       │  Authorization: Bearer <token>
       │
       ▼
┌─────────────┐      GET /api/v1/...        ┌─────────────────┐
│   Client    │ ──────────────────────────▶ │  Ablage-System  │
│             │ ◀────────────────────────── │                 │
└─────────────┘         Response            └─────────────────┘
```

**Token-Ablauf:**
- Access Token: 30 Minuten
- Refresh Token: 7 Tage

**Token-Refresh:**

```bash
POST /api/v1/auth/refresh
Content-Type: application/json

{
  "refresh_token": "<refresh_token>"
}

# Response
{
  "access_token": "<new_access_token>",
  "token_type": "bearer",
  "expires_in": 1800
}
```

### API-Key-Authentifizierung

Für Server-zu-Server-Integration empfehlen wir API-Keys:

```bash
# API-Key erstellen (Admin)
POST /api/v1/admin/api-keys
Content-Type: application/json
Authorization: Bearer <admin_token>

{
  "name": "ERP-Integration",
  "scopes": ["documents:read", "documents:write", "ocr:process"],
  "expires_at": "2026-01-01T00:00:00Z"
}

# Response
{
  "id": "key_abc123",
  "api_key": "sk_live_xxxxxxxxxxxxxxxxxxxx",  # Nur einmal angezeigt!
  "name": "ERP-Integration",
  "scopes": ["documents:read", "documents:write", "ocr:process"],
  "created_at": "2025-01-08T10:00:00Z",
  "expires_at": "2026-01-01T00:00:00Z"
}
```

**Verwendung:**

```bash
curl -H "X-API-Key: sk_live_xxxxxxxxxxxxxxxxxxxx" \
  "http://localhost:8000/api/v1/documents/"
```

### OAuth 2.0 (Enterprise)

Für Enterprise-Integrationen mit SSO:

```
Client ID: ablage-system
Authorize URL: https://ablage.firma.de/oauth/authorize
Token URL: https://ablage.firma.de/oauth/token
Scopes: openid profile email documents
```

---

## Webhooks

### Webhook-Konfiguration

Registrieren Sie Webhooks für Echtzeit-Benachrichtigungen:

```bash
POST /api/v1/webhooks
Content-Type: application/json
Authorization: Bearer <token>

{
  "url": "https://your-system.com/ablage-webhook",
  "events": [
    "document.created",
    "document.processed",
    "document.failed",
    "document.deleted"
  ],
  "secret": "your_webhook_secret",
  "active": true
}
```

### Verfügbare Events

| Event | Beschreibung | Payload |
|-------|--------------|---------|
| `document.created` | Dokument hochgeladen | `{id, filename, status}` |
| `document.processed` | OCR abgeschlossen | `{id, filename, extracted_text, document_type}` |
| `document.failed` | Verarbeitung fehlgeschlagen | `{id, filename, error}` |
| `document.deleted` | Dokument gelöscht | `{id, filename, deleted_at}` |
| `document.updated` | Dokument aktualisiert | `{id, filename, changes}` |
| `batch.completed` | Batch-Job abgeschlossen | `{batch_id, total, succeeded, failed}` |

### Webhook-Payload

```json
{
  "id": "evt_abc123",
  "type": "document.processed",
  "created_at": "2025-01-08T10:30:00Z",
  "data": {
    "document": {
      "id": "doc_xyz789",
      "filename": "rechnung_2025-01.pdf",
      "status": "completed",
      "document_type": "invoice",
      "extracted_text": "Rechnung Nr. 12345...",
      "confidence": 0.95,
      "extracted_data": {
        "invoice_number": "12345",
        "date": "2025-01-05",
        "total_amount": 1234.56,
        "vendor": "Muster GmbH"
      }
    }
  }
}
```

### Webhook-Signatur-Verifizierung

Alle Webhooks werden mit HMAC-SHA256 signiert:

```python
import hmac
import hashlib

def verify_webhook(payload: bytes, signature: str, secret: str) -> bool:
    """Verifiziert die Webhook-Signatur."""
    expected = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(f"sha256={expected}", signature)

# Verwendung in Flask/FastAPI
@app.post("/ablage-webhook")
async def handle_webhook(request: Request):
    payload = await request.body()
    signature = request.headers.get("X-Ablage-Signature")

    if not verify_webhook(payload, signature, WEBHOOK_SECRET):
        raise HTTPException(401, "Invalid signature")

    data = json.loads(payload)
    # Event verarbeiten...
```

### Retry-Logik

Bei Webhook-Fehlern:

| Versuch | Wartezeit |
|---------|-----------|
| 1 | Sofort |
| 2 | 1 Minute |
| 3 | 5 Minuten |
| 4 | 30 Minuten |
| 5 | 2 Stunden |

Nach 5 fehlgeschlagenen Versuchen wird der Webhook deaktiviert.

---

## ERP-Integration

### SAP-Integration

```python
"""SAP Business One Integration"""

from ablage_client import AblageClient
import pyrfc  # SAP RFC Connector

class SAPIntegration:
    def __init__(self, ablage_url: str, sap_config: dict):
        self.ablage = AblageClient(ablage_url)
        self.sap = pyrfc.Connection(**sap_config)

    async def process_invoice(self, document_id: str):
        """Verarbeitet Rechnung und erstellt SAP-Beleg."""
        # 1. Dokument aus Ablage abrufen
        doc = await self.ablage.get_document(document_id)

        if doc.document_type != "invoice":
            raise ValueError("Dokument ist keine Rechnung")

        # 2. Extrahierte Daten
        data = doc.extracted_data

        # 3. SAP-Beleg erstellen
        result = self.sap.call("BAPI_ACC_DOCUMENT_POST", {
            "DOCUMENTHEADER": {
                "COMP_CODE": "1000",
                "DOC_DATE": data["date"],
                "DOC_TYPE": "KR",  # Kreditorenrechnung
                "REF_DOC_NO": data["invoice_number"],
            },
            "ACCOUNTGL": [{
                "ITEMNO_ACC": "1",
                "GL_ACCOUNT": "400000",  # Aufwandskonto
                "COMP_CODE": "1000",
                "AMOUNT": data["total_amount"],
            }],
            "ACCOUNTPAYABLE": [{
                "ITEMNO_ACC": "2",
                "VENDOR_NO": self._find_vendor(data["vendor"]),
                "COMP_CODE": "1000",
            }]
        })

        return result

    def _find_vendor(self, vendor_name: str) -> str:
        """Findet Kreditor-Nummer anhand Name."""
        result = self.sap.call("BAPI_VENDOR_FIND", {
            "MAX_CNT": 1,
            "NAME1": vendor_name
        })
        if result["VENDOR_LIST"]:
            return result["VENDOR_LIST"][0]["VENDOR_NO"]
        raise ValueError(f"Kreditor nicht gefunden: {vendor_name}")
```

### Microsoft Dynamics 365

```typescript
/**
 * Dynamics 365 Integration
 */

import { Client } from "@microsoft/microsoft-graph-client";
import { AblageClient } from "./ablage-client";

class DynamicsIntegration {
  private ablage: AblageClient;
  private dynamics: Client;

  constructor(ablageUrl: string, dynamicsConfig: DynamicsConfig) {
    this.ablage = new AblageClient(ablageUrl);
    this.dynamics = Client.init({
      authProvider: (done) => {
        done(null, dynamicsConfig.accessToken);
      },
    });
  }

  async syncInvoice(documentId: string): Promise<void> {
    // Dokument abrufen
    const doc = await this.ablage.getDocument(documentId);
    const data = doc.extracted_data;

    // Dynamics Purchase Invoice erstellen
    await this.dynamics
      .api("/purchaseInvoices")
      .post({
        vendorNumber: await this.findVendor(data.vendor),
        invoiceDate: data.date,
        vendorInvoiceNumber: data.invoice_number,
        purchaseInvoiceLines: [
          {
            lineType: "Item",
            itemId: await this.mapItem(data.items[0]),
            quantity: data.items[0].quantity,
            unitPrice: data.items[0].unit_price,
          },
        ],
      });
  }

  private async findVendor(name: string): Promise<string> {
    const result = await this.dynamics
      .api("/vendors")
      .filter(`displayName eq '${name}'`)
      .get();

    if (result.value.length === 0) {
      throw new Error(`Vendor not found: ${name}`);
    }

    return result.value[0].number;
  }
}
```

---

## DMS-Integration

### SharePoint Online

```python
"""SharePoint Online Integration"""

from office365.sharepoint.client_context import ClientContext
from office365.runtime.auth.user_credential import UserCredential
from ablage_client import AblageClient

class SharePointIntegration:
    def __init__(
        self,
        ablage_url: str,
        sharepoint_url: str,
        username: str,
        password: str
    ):
        self.ablage = AblageClient(ablage_url)
        self.ctx = ClientContext(sharepoint_url).with_credentials(
            UserCredential(username, password)
        )

    async def sync_to_sharepoint(
        self,
        document_id: str,
        library_name: str = "Dokumente"
    ):
        """Synchronisiert Dokument zu SharePoint."""
        # Dokument herunterladen
        doc = await self.ablage.get_document(document_id)
        content = await self.ablage.download_document_content(document_id)

        # Ordnerstruktur nach Dokumenttyp
        folder_path = f"{library_name}/{doc.document_type}/{doc.created_at.year}"

        # Ordner erstellen (falls nicht vorhanden)
        target_folder = self.ctx.web.ensure_folder_path(folder_path)
        self.ctx.execute_query()

        # Datei hochladen
        target_folder.upload_file(doc.filename, content).execute_query()

        # Metadaten setzen
        file_item = target_folder.files.get_by_url(doc.filename).listItemAllFields
        file_item.set_property("AblageDocumentId", document_id)
        file_item.set_property("OCRConfidence", doc.confidence)
        file_item.update().execute_query()

    async def watch_sharepoint_folder(
        self,
        library_name: str,
        folder_path: str
    ):
        """Überwacht SharePoint-Ordner und lädt neue Dateien hoch."""
        target_folder = self.ctx.web.get_folder_by_server_relative_url(
            f"{library_name}/{folder_path}"
        )
        files = target_folder.files
        self.ctx.load(files)
        self.ctx.execute_query()

        for file in files:
            # Prüfen ob bereits verarbeitet
            if self._is_processed(file):
                continue

            # Datei herunterladen
            content = file.read()
            self.ctx.execute_query()

            # In Ablage-System hochladen
            doc = await self.ablage.upload_document_content(
                content,
                file.name
            )

            # Als verarbeitet markieren
            self._mark_processed(file, doc.id)
```

### Alfresco

```python
"""Alfresco ECM Integration"""

from cmislib import CmisClient
from ablage_client import AblageClient

class AlfrescoIntegration:
    def __init__(
        self,
        ablage_url: str,
        alfresco_url: str,
        username: str,
        password: str
    ):
        self.ablage = AblageClient(ablage_url)
        self.cmis = CmisClient(
            f"{alfresco_url}/alfresco/api/-default-/public/cmis/versions/1.1/atom",
            username,
            password
        )
        self.repo = self.cmis.defaultRepository

    async def sync_document(self, document_id: str, folder_path: str):
        """Synchronisiert Dokument zu Alfresco."""
        doc = await self.ablage.get_document(document_id)
        content = await self.ablage.download_document_content(document_id)

        # Ordner finden oder erstellen
        folder = self._get_or_create_folder(folder_path)

        # Dokument erstellen
        new_doc = folder.createDocument(
            doc.filename,
            contentFile=content,
            properties={
                "cmis:name": doc.filename,
                "ablage:documentId": document_id,
                "ablage:documentType": doc.document_type,
                "ablage:ocrConfidence": str(doc.confidence),
                "ablage:extractedText": doc.extracted_text[:1000],
            }
        )

        return new_doc.id

    def _get_or_create_folder(self, path: str):
        """Erstellt Ordnerstruktur rekursiv."""
        parts = path.strip("/").split("/")
        current = self.repo.rootFolder

        for part in parts:
            try:
                current = current.getObjectByPath(part)
            except:
                current = current.createFolder(part)

        return current
```

---

## E-Mail-Integration

### Automatische E-Mail-Verarbeitung

```python
"""E-Mail zu Ablage-System Pipeline"""

import imaplib
import email
from email.header import decode_header
from pathlib import Path
from ablage_client import AblageClient

class EmailProcessor:
    def __init__(
        self,
        ablage_url: str,
        imap_server: str,
        email_user: str,
        email_password: str
    ):
        self.ablage = AblageClient(ablage_url)
        self.imap = imaplib.IMAP4_SSL(imap_server)
        self.imap.login(email_user, email_password)

    async def process_inbox(self, folder: str = "INBOX"):
        """Verarbeitet alle ungelesenen E-Mails mit Anhängen."""
        self.imap.select(folder)

        # Ungelesene E-Mails suchen
        _, message_ids = self.imap.search(None, "UNSEEN")

        for msg_id in message_ids[0].split():
            _, msg_data = self.imap.fetch(msg_id, "(RFC822)")
            email_msg = email.message_from_bytes(msg_data[0][1])

            # Anhänge verarbeiten
            for part in email_msg.walk():
                if part.get_content_maintype() == "multipart":
                    continue

                filename = part.get_filename()
                if not filename:
                    continue

                # Nur unterstützte Formate
                if not self._is_supported(filename):
                    continue

                # Anhang speichern
                content = part.get_payload(decode=True)
                temp_path = Path(f"/tmp/{filename}")
                temp_path.write_bytes(content)

                # In Ablage-System hochladen
                doc = await self.ablage.upload_document(temp_path)

                # Metadaten aus E-Mail
                await self.ablage.update_document(doc.id, {
                    "source": "email",
                    "email_from": self._decode_header(email_msg["From"]),
                    "email_subject": self._decode_header(email_msg["Subject"]),
                    "email_date": email_msg["Date"],
                })

                temp_path.unlink()

            # E-Mail als gelesen markieren
            self.imap.store(msg_id, "+FLAGS", "\\Seen")

    def _is_supported(self, filename: str) -> bool:
        """Prüft ob Dateiformat unterstützt wird."""
        supported = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif"}
        return Path(filename).suffix.lower() in supported

    def _decode_header(self, header: str) -> str:
        """Dekodiert E-Mail-Header."""
        decoded = decode_header(header)[0]
        if isinstance(decoded[0], bytes):
            return decoded[0].decode(decoded[1] or "utf-8")
        return decoded[0]


# Cron-Job für stündliche Verarbeitung
if __name__ == "__main__":
    import asyncio

    processor = EmailProcessor(
        ablage_url="http://localhost:8000",
        imap_server="imap.firma.de",
        email_user="rechnungen@firma.de",
        email_password="password"
    )

    asyncio.run(processor.process_inbox())
```

---

## Workflow-Automatisierung

### n8n Integration

```json
{
  "name": "Ablage-System Rechnungsworkflow",
  "nodes": [
    {
      "name": "Webhook Trigger",
      "type": "n8n-nodes-base.webhook",
      "parameters": {
        "path": "ablage-invoice",
        "httpMethod": "POST",
        "authentication": "headerAuth"
      }
    },
    {
      "name": "Parse Webhook",
      "type": "n8n-nodes-base.set",
      "parameters": {
        "values": {
          "string": [
            {
              "name": "document_id",
              "value": "={{ $json.data.document.id }}"
            },
            {
              "name": "invoice_number",
              "value": "={{ $json.data.document.extracted_data.invoice_number }}"
            },
            {
              "name": "amount",
              "value": "={{ $json.data.document.extracted_data.total_amount }}"
            }
          ]
        }
      }
    },
    {
      "name": "Check Amount",
      "type": "n8n-nodes-base.if",
      "parameters": {
        "conditions": {
          "number": [
            {
              "value1": "={{ $json.amount }}",
              "operation": "larger",
              "value2": 1000
            }
          ]
        }
      }
    },
    {
      "name": "Create Approval Task",
      "type": "n8n-nodes-base.httpRequest",
      "parameters": {
        "url": "https://tasks.firma.de/api/tasks",
        "method": "POST",
        "body": {
          "title": "Rechnung genehmigen: {{ $json.invoice_number }}",
          "amount": "{{ $json.amount }}",
          "document_link": "https://ablage.firma.de/documents/{{ $json.document_id }}"
        }
      }
    },
    {
      "name": "Slack Notification",
      "type": "n8n-nodes-base.slack",
      "parameters": {
        "channel": "#rechnungen",
        "text": "Neue Rechnung: {{ $json.invoice_number }} ({{ $json.amount }} EUR)"
      }
    }
  ]
}
```

### Zapier Integration

```javascript
// Zapier Code Step: Ablage-System Webhook Handler

const payload = inputData.payload;
const document = JSON.parse(payload).data.document;

// Rechnungsdaten extrahieren
const invoiceData = {
  documentId: document.id,
  filename: document.filename,
  invoiceNumber: document.extracted_data?.invoice_number || 'N/A',
  date: document.extracted_data?.date || new Date().toISOString(),
  amount: document.extracted_data?.total_amount || 0,
  vendor: document.extracted_data?.vendor || 'Unbekannt',
  status: document.status,
  confidence: document.confidence
};

// Ausgabe für nächsten Zapier-Step
output = [invoiceData];
```

---

## DATEV-Export

### Export-Formate

Das Ablage-System unterstützt DATEV-konforme Exporte:

| Format | Beschreibung |
|--------|--------------|
| DATEV CSV | Standard Buchungssätze |
| DATEV XML | Strukturierte Buchungsdaten |
| DATEV Beleglink | Belegverknüpfung |

### CSV-Export

```bash
POST /api/v1/export/datev
Content-Type: application/json
Authorization: Bearer <token>

{
  "document_ids": ["doc_abc", "doc_xyz"],
  "format": "csv",
  "date_from": "2025-01-01",
  "date_to": "2025-01-31",
  "include_documents": true
}

# Response
{
  "export_id": "exp_123",
  "status": "processing",
  "download_url": null
}

# Nach Verarbeitung
GET /api/v1/export/exp_123

{
  "export_id": "exp_123",
  "status": "completed",
  "download_url": "/api/v1/export/exp_123/download",
  "files": [
    "EXTF_Buchungsstapel.csv",
    "Belege/"
  ]
}
```

### DATEV CSV Format

```csv
"Umsatz (ohne Soll/Haben-Kz)";"Soll/Haben-Kennzeichen";"WKZ Umsatz";"Kurs";"Basis-Umsatz";"WKZ Basis-Umsatz";"Konto";"Gegenkonto (ohne BU-Schlüssel)";"BU-Schlüssel";"Belegdatum";"Belegfeld 1";"Belegfeld 2";"Skonto";"Buchungstext"
1234,56;"S";"";"";"";"";70000;1200;"";"0501";"RE-12345";"";"";"";"Rechnung Muster GmbH"
```

### Python Export-Client

```python
from ablage_client import AblageClient
from pathlib import Path

async def export_month_to_datev(year: int, month: int):
    """Exportiert alle Rechnungen eines Monats für DATEV."""
    client = AblageClient()
    await client.login("buchhalter@firma.de", "password")

    # Rechnungen des Monats abrufen
    date_from = f"{year}-{month:02d}-01"
    date_to = f"{year}-{month:02d}-31"

    documents = await client.list_documents(
        document_type="invoice",
        status="completed",
        date_from=date_from,
        date_to=date_to
    )

    # DATEV-Export starten
    export = await client.create_datev_export(
        document_ids=[d.id for d in documents],
        format="csv",
        include_documents=True
    )

    # Auf Export warten
    while export.status == "processing":
        await asyncio.sleep(5)
        export = await client.get_export(export.id)

    # Download
    await client.download_export(
        export.id,
        Path(f"./datev_export_{year}_{month:02d}.zip")
    )

    print(f"Export abgeschlossen: {len(documents)} Dokumente")
```

---

## Best Practices

### Fehlerbehandlung

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=60)
)
async def upload_with_retry(client, file_path):
    """Upload mit automatischem Retry."""
    return await client.upload_document(file_path)
```

### Rate Limiting beachten

```python
import asyncio
from asyncio import Semaphore

class RateLimitedClient:
    def __init__(self, client, max_concurrent: int = 10):
        self.client = client
        self.semaphore = Semaphore(max_concurrent)

    async def upload(self, file_path):
        async with self.semaphore:
            return await self.client.upload_document(file_path)
```

### Idempotenz

```python
async def safe_upload(client, file_path, idempotency_key: str):
    """Idempotenter Upload mit Deduplizierung."""
    # Prüfen ob bereits vorhanden
    existing = await client.search_documents(
        f"idempotency_key:{idempotency_key}"
    )
    if existing:
        return existing[0]

    # Neuer Upload mit Key
    return await client.upload_document(
        file_path,
        metadata={"idempotency_key": idempotency_key}
    )
```

---

## Support

Bei Integrationsfragen:

- **Dokumentation**: `/api/v1/docs` (OpenAPI)
- **E-Mail**: integration@firma.de
- **Ticket**: Jira ABLAGE-INTEGRATION

---

*Letzte Aktualisierung: Januar 2025*
