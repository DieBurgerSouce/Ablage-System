# SDK Examples

> **Ablage-System - Code-Beispiele für API-Integration**
> Version: 1.0 | Stand: Januar 2025

---

## Übersicht

Dieses Dokument enthält praktische Beispiele für die Integration mit der Ablage-System API in verschiedenen Programmiersprachen:

- [Python](#python-beispiele)
- [JavaScript/TypeScript](#javascripttypescript-beispiele)
- [cURL](#curl-beispiele)
- [PowerShell](#powershell-beispiele)

---

## Python Beispiele

### Installation

```bash
pip install httpx python-multipart
```

### Client-Klasse

```python
"""
Ablage-System Python SDK
Einfacher API-Client für das Ablage-System.
"""

import httpx
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Document:
    """Repräsentiert ein Dokument im Ablage-System."""
    id: str
    filename: str
    status: str
    created_at: datetime
    extracted_text: Optional[str] = None
    document_type: Optional[str] = None
    confidence: Optional[float] = None


class AblageClient:
    """Client für die Ablage-System API."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        api_key: Optional[str] = None,
        timeout: float = 30.0
    ):
        """
        Initialisiert den API-Client.

        Args:
            base_url: Basis-URL des Ablage-Systems
            api_key: API-Schlüssel für Authentifizierung
            timeout: Request-Timeout in Sekunden
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)
        self._access_token: Optional[str] = None

        if api_key:
            self._client.headers["X-API-Key"] = api_key

    def login(self, email: str, password: str) -> bool:
        """
        Authentifiziert den Benutzer und speichert das Token.

        Args:
            email: Benutzer-E-Mail
            password: Passwort

        Returns:
            True bei erfolgreicher Anmeldung
        """
        response = self._client.post(
            f"{self.base_url}/api/v1/auth/login",
            data={"username": email, "password": password}
        )
        response.raise_for_status()

        data = response.json()
        self._access_token = data["access_token"]
        self._client.headers["Authorization"] = f"Bearer {self._access_token}"
        return True

    def health_check(self) -> Dict[str, Any]:
        """Prüft den System-Status."""
        response = self._client.get(f"{self.base_url}/api/v1/health")
        response.raise_for_status()
        return response.json()

    # === Dokument-Operationen ===

    def upload_document(
        self,
        file_path: Path,
        ocr_backend: str = "auto",
        priority: int = 5
    ) -> Document:
        """
        Lädt ein Dokument hoch und startet OCR-Verarbeitung.

        Args:
            file_path: Pfad zur Datei
            ocr_backend: OCR-Backend (auto, deepseek, got_ocr, surya)
            priority: Verarbeitungspriorität (1-10)

        Returns:
            Das erstellte Document-Objekt
        """
        with open(file_path, "rb") as f:
            files = {"file": (file_path.name, f, self._get_mime_type(file_path))}
            data = {"ocr_backend": ocr_backend, "priority": priority}

            response = self._client.post(
                f"{self.base_url}/api/v1/documents/",
                files=files,
                data=data
            )
            response.raise_for_status()

        return self._parse_document(response.json())

    def get_document(self, document_id: str) -> Document:
        """Ruft ein Dokument ab."""
        response = self._client.get(
            f"{self.base_url}/api/v1/documents/{document_id}"
        )
        response.raise_for_status()
        return self._parse_document(response.json())

    def list_documents(
        self,
        status: Optional[str] = None,
        document_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Document]:
        """
        Listet Dokumente mit optionalen Filtern.

        Args:
            status: Filter nach Status (pending, processing, completed, failed)
            document_type: Filter nach Dokumenttyp
            limit: Maximale Anzahl
            offset: Offset für Paginierung

        Returns:
            Liste von Document-Objekten
        """
        params = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status
        if document_type:
            params["document_type"] = document_type

        response = self._client.get(
            f"{self.base_url}/api/v1/documents/",
            params=params
        )
        response.raise_for_status()

        data = response.json()
        return [self._parse_document(doc) for doc in data["items"]]

    def search_documents(
        self,
        query: str,
        limit: int = 20
    ) -> List[Document]:
        """
        Durchsucht Dokumente nach Stichworten.

        Args:
            query: Suchbegriff
            limit: Maximale Anzahl Ergebnisse

        Returns:
            Liste gefundener Dokumente
        """
        response = self._client.get(
            f"{self.base_url}/api/v1/documents/search",
            params={"q": query, "limit": limit}
        )
        response.raise_for_status()

        data = response.json()
        return [self._parse_document(doc) for doc in data["items"]]

    def delete_document(self, document_id: str) -> bool:
        """Löscht ein Dokument (Soft-Delete)."""
        response = self._client.delete(
            f"{self.base_url}/api/v1/documents/{document_id}"
        )
        response.raise_for_status()
        return True

    def download_document(
        self,
        document_id: str,
        output_path: Path
    ) -> Path:
        """
        Lädt ein Dokument herunter.

        Args:
            document_id: Dokument-ID
            output_path: Zielpfad für Download

        Returns:
            Pfad zur heruntergeladenen Datei
        """
        response = self._client.get(
            f"{self.base_url}/api/v1/documents/{document_id}/download",
            follow_redirects=True
        )
        response.raise_for_status()

        with open(output_path, "wb") as f:
            f.write(response.content)

        return output_path

    # === OCR-Operationen ===

    def get_ocr_status(self, document_id: str) -> Dict[str, Any]:
        """Ruft den OCR-Verarbeitungsstatus ab."""
        response = self._client.get(
            f"{self.base_url}/api/v1/ocr/{document_id}/status"
        )
        response.raise_for_status()
        return response.json()

    def reprocess_document(
        self,
        document_id: str,
        backend: str = "deepseek"
    ) -> Dict[str, Any]:
        """Startet OCR-Verarbeitung erneut."""
        response = self._client.post(
            f"{self.base_url}/api/v1/ocr/{document_id}/reprocess",
            json={"backend": backend}
        )
        response.raise_for_status()
        return response.json()

    # === Batch-Operationen ===

    def batch_upload(
        self,
        file_paths: List[Path],
        ocr_backend: str = "auto"
    ) -> List[Document]:
        """
        Lädt mehrere Dokumente hoch.

        Args:
            file_paths: Liste von Dateipfaden
            ocr_backend: OCR-Backend für alle Dokumente

        Returns:
            Liste erstellter Dokumente
        """
        documents = []
        for file_path in file_paths:
            doc = self.upload_document(file_path, ocr_backend)
            documents.append(doc)
        return documents

    def wait_for_processing(
        self,
        document_id: str,
        timeout: int = 300,
        poll_interval: int = 2
    ) -> Document:
        """
        Wartet auf Abschluss der OCR-Verarbeitung.

        Args:
            document_id: Dokument-ID
            timeout: Maximale Wartezeit in Sekunden
            poll_interval: Abfrage-Intervall in Sekunden

        Returns:
            Das verarbeitete Dokument

        Raises:
            TimeoutError: Wenn Timeout überschritten
        """
        import time
        start = time.time()

        while time.time() - start < timeout:
            doc = self.get_document(document_id)
            if doc.status in ("completed", "failed"):
                return doc
            time.sleep(poll_interval)

        raise TimeoutError(
            f"Dokument {document_id} nicht innerhalb von {timeout}s verarbeitet"
        )

    # === Hilfsmethoden ===

    def _parse_document(self, data: Dict[str, Any]) -> Document:
        """Parst API-Response zu Document-Objekt."""
        return Document(
            id=data["id"],
            filename=data["filename"],
            status=data["status"],
            created_at=datetime.fromisoformat(data["created_at"]),
            extracted_text=data.get("extracted_text"),
            document_type=data.get("document_type"),
            confidence=data.get("confidence")
        )

    def _get_mime_type(self, file_path: Path) -> str:
        """Ermittelt MIME-Type basierend auf Dateiendung."""
        mime_types = {
            ".pdf": "application/pdf",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".tiff": "image/tiff",
            ".tif": "image/tiff",
            ".webp": "image/webp"
        }
        return mime_types.get(file_path.suffix.lower(), "application/octet-stream")

    def close(self):
        """Schließt den HTTP-Client."""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# === Verwendungsbeispiele ===

if __name__ == "__main__":
    # Beispiel 1: Einfacher Upload
    with AblageClient() as client:
        client.login("user@example.com", "password")

        # Dokument hochladen
        doc = client.upload_document(Path("rechnung.pdf"))
        print(f"Dokument erstellt: {doc.id}")

        # Auf Verarbeitung warten
        processed = client.wait_for_processing(doc.id)
        print(f"Text: {processed.extracted_text[:200]}...")

    # Beispiel 2: Batch-Upload
    with AblageClient() as client:
        client.login("user@example.com", "password")

        files = [
            Path("dokument1.pdf"),
            Path("dokument2.pdf"),
            Path("dokument3.pdf")
        ]
        docs = client.batch_upload(files)
        print(f"{len(docs)} Dokumente hochgeladen")

    # Beispiel 3: Suche
    with AblageClient() as client:
        client.login("user@example.com", "password")

        results = client.search_documents("Rechnung 2025")
        for doc in results:
            print(f"- {doc.filename}: {doc.document_type}")
```

### Async-Client

```python
"""
Ablage-System Async Python SDK
Asynchroner API-Client für hohen Durchsatz.
"""

import httpx
import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Any


class AsyncAblageClient:
    """Asynchroner Client für die Ablage-System API."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        timeout: float = 30.0
    ):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout)
        self._access_token: Optional[str] = None

    async def login(self, email: str, password: str) -> bool:
        """Authentifiziert den Benutzer."""
        response = await self._client.post(
            f"{self.base_url}/api/v1/auth/login",
            data={"username": email, "password": password}
        )
        response.raise_for_status()

        data = response.json()
        self._access_token = data["access_token"]
        self._client.headers["Authorization"] = f"Bearer {self._access_token}"
        return True

    async def upload_document(self, file_path: Path) -> Dict[str, Any]:
        """Lädt ein Dokument asynchron hoch."""
        with open(file_path, "rb") as f:
            files = {"file": (file_path.name, f)}
            response = await self._client.post(
                f"{self.base_url}/api/v1/documents/",
                files=files
            )
            response.raise_for_status()
            return response.json()

    async def upload_many(
        self,
        file_paths: List[Path],
        concurrency: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Lädt viele Dokumente parallel hoch.

        Args:
            file_paths: Liste von Dateipfaden
            concurrency: Maximale parallele Uploads

        Returns:
            Liste der erstellten Dokumente
        """
        semaphore = asyncio.Semaphore(concurrency)

        async def upload_with_limit(path: Path) -> Dict[str, Any]:
            async with semaphore:
                return await self.upload_document(path)

        tasks = [upload_with_limit(path) for path in file_paths]
        return await asyncio.gather(*tasks)

    async def wait_for_all(
        self,
        document_ids: List[str],
        timeout: int = 300
    ) -> List[Dict[str, Any]]:
        """Wartet auf Verarbeitung mehrerer Dokumente."""
        async def wait_for_one(doc_id: str) -> Dict[str, Any]:
            while True:
                response = await self._client.get(
                    f"{self.base_url}/api/v1/documents/{doc_id}"
                )
                doc = response.json()
                if doc["status"] in ("completed", "failed"):
                    return doc
                await asyncio.sleep(2)

        tasks = [
            asyncio.wait_for(wait_for_one(doc_id), timeout=timeout)
            for doc_id in document_ids
        ]
        return await asyncio.gather(*tasks)

    async def close(self):
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


# Beispiel: Async Batch-Verarbeitung
async def process_folder(folder: Path):
    """Verarbeitet alle PDFs in einem Ordner."""
    files = list(folder.glob("*.pdf"))
    print(f"Gefunden: {len(files)} Dokumente")

    async with AsyncAblageClient() as client:
        await client.login("user@example.com", "password")

        # Parallel hochladen
        results = await client.upload_many(files, concurrency=10)
        doc_ids = [r["id"] for r in results]
        print(f"Hochgeladen: {len(doc_ids)} Dokumente")

        # Auf Verarbeitung warten
        processed = await client.wait_for_all(doc_ids, timeout=600)
        completed = sum(1 for d in processed if d["status"] == "completed")
        print(f"Verarbeitet: {completed}/{len(processed)}")


if __name__ == "__main__":
    asyncio.run(process_folder(Path("./dokumente")))
```

---

## JavaScript/TypeScript Beispiele

### Installation

```bash
npm install axios form-data
# TypeScript
npm install --save-dev typescript @types/node
```

### TypeScript Client

```typescript
/**
 * Ablage-System TypeScript SDK
 */

import axios, { AxiosInstance, AxiosError } from 'axios';
import FormData from 'form-data';
import * as fs from 'fs';
import * as path from 'path';

interface Document {
  id: string;
  filename: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  created_at: string;
  extracted_text?: string;
  document_type?: string;
  confidence?: number;
}

interface PaginatedResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

interface UploadOptions {
  ocrBackend?: 'auto' | 'deepseek' | 'got_ocr' | 'surya';
  priority?: number;
}

export class AblageClient {
  private client: AxiosInstance;
  private accessToken?: string;

  constructor(
    private baseUrl: string = 'http://localhost:8000',
    private timeout: number = 30000
  ) {
    this.client = axios.create({
      baseURL: baseUrl,
      timeout: timeout,
      headers: {
        'Content-Type': 'application/json',
      },
    });
  }

  /**
   * Authentifiziert den Benutzer
   */
  async login(email: string, password: string): Promise<void> {
    const formData = new URLSearchParams();
    formData.append('username', email);
    formData.append('password', password);

    const response = await this.client.post('/api/v1/auth/login', formData, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    });

    this.accessToken = response.data.access_token;
    this.client.defaults.headers.common['Authorization'] =
      `Bearer ${this.accessToken}`;
  }

  /**
   * Prüft System-Gesundheit
   */
  async healthCheck(): Promise<Record<string, unknown>> {
    const response = await this.client.get('/api/v1/health');
    return response.data;
  }

  // === Dokument-Operationen ===

  /**
   * Lädt ein Dokument hoch
   */
  async uploadDocument(
    filePath: string,
    options: UploadOptions = {}
  ): Promise<Document> {
    const form = new FormData();
    form.append('file', fs.createReadStream(filePath));

    if (options.ocrBackend) {
      form.append('ocr_backend', options.ocrBackend);
    }
    if (options.priority) {
      form.append('priority', options.priority.toString());
    }

    const response = await this.client.post('/api/v1/documents/', form, {
      headers: form.getHeaders(),
    });

    return response.data;
  }

  /**
   * Ruft ein Dokument ab
   */
  async getDocument(documentId: string): Promise<Document> {
    const response = await this.client.get(`/api/v1/documents/${documentId}`);
    return response.data;
  }

  /**
   * Listet Dokumente auf
   */
  async listDocuments(params?: {
    status?: string;
    documentType?: string;
    limit?: number;
    offset?: number;
  }): Promise<PaginatedResponse<Document>> {
    const response = await this.client.get('/api/v1/documents/', { params });
    return response.data;
  }

  /**
   * Durchsucht Dokumente
   */
  async searchDocuments(
    query: string,
    limit: number = 20
  ): Promise<PaginatedResponse<Document>> {
    const response = await this.client.get('/api/v1/documents/search', {
      params: { q: query, limit },
    });
    return response.data;
  }

  /**
   * Löscht ein Dokument
   */
  async deleteDocument(documentId: string): Promise<void> {
    await this.client.delete(`/api/v1/documents/${documentId}`);
  }

  /**
   * Lädt Dokument-Datei herunter
   */
  async downloadDocument(
    documentId: string,
    outputPath: string
  ): Promise<void> {
    const response = await this.client.get(
      `/api/v1/documents/${documentId}/download`,
      { responseType: 'stream' }
    );

    const writer = fs.createWriteStream(outputPath);
    response.data.pipe(writer);

    return new Promise((resolve, reject) => {
      writer.on('finish', resolve);
      writer.on('error', reject);
    });
  }

  // === OCR-Operationen ===

  /**
   * Ruft OCR-Status ab
   */
  async getOcrStatus(documentId: string): Promise<Record<string, unknown>> {
    const response = await this.client.get(`/api/v1/ocr/${documentId}/status`);
    return response.data;
  }

  /**
   * Startet OCR erneut
   */
  async reprocessDocument(
    documentId: string,
    backend: string = 'deepseek'
  ): Promise<Record<string, unknown>> {
    const response = await this.client.post(
      `/api/v1/ocr/${documentId}/reprocess`,
      { backend }
    );
    return response.data;
  }

  // === Hilfsmethoden ===

  /**
   * Wartet auf Verarbeitung
   */
  async waitForProcessing(
    documentId: string,
    timeoutMs: number = 300000,
    pollIntervalMs: number = 2000
  ): Promise<Document> {
    const startTime = Date.now();

    while (Date.now() - startTime < timeoutMs) {
      const doc = await this.getDocument(documentId);

      if (doc.status === 'completed' || doc.status === 'failed') {
        return doc;
      }

      await this.sleep(pollIntervalMs);
    }

    throw new Error(
      `Timeout: Dokument ${documentId} nicht innerhalb von ${timeoutMs}ms verarbeitet`
    );
  }

  /**
   * Lädt mehrere Dokumente hoch
   */
  async batchUpload(
    filePaths: string[],
    options: UploadOptions = {}
  ): Promise<Document[]> {
    const results: Document[] = [];

    for (const filePath of filePaths) {
      const doc = await this.uploadDocument(filePath, options);
      results.push(doc);
    }

    return results;
  }

  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
}

// === Verwendungsbeispiele ===

async function main() {
  const client = new AblageClient('http://localhost:8000');

  try {
    // Anmelden
    await client.login('user@example.com', 'password');
    console.log('Angemeldet');

    // Dokument hochladen
    const doc = await client.uploadDocument('./rechnung.pdf', {
      ocrBackend: 'deepseek',
    });
    console.log(`Dokument erstellt: ${doc.id}`);

    // Auf Verarbeitung warten
    const processed = await client.waitForProcessing(doc.id);
    console.log(`Status: ${processed.status}`);
    console.log(`Text: ${processed.extracted_text?.substring(0, 200)}...`);

    // Suchen
    const results = await client.searchDocuments('Rechnung');
    console.log(`Gefunden: ${results.total} Dokumente`);
  } catch (error) {
    if (axios.isAxiosError(error)) {
      console.error(`API Fehler: ${error.response?.status} - ${error.message}`);
    } else {
      throw error;
    }
  }
}

main();
```

### React Hook

```typescript
/**
 * React Hook für Ablage-System
 */

import { useState, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { AblageClient, Document } from './ablage-client';

const client = new AblageClient();

export function useDocuments(params?: {
  status?: string;
  limit?: number;
  offset?: number;
}) {
  return useQuery({
    queryKey: ['documents', params],
    queryFn: () => client.listDocuments(params),
  });
}

export function useDocument(documentId: string) {
  return useQuery({
    queryKey: ['document', documentId],
    queryFn: () => client.getDocument(documentId),
    refetchInterval: (data) =>
      data?.status === 'processing' ? 2000 : false,
  });
}

export function useUploadDocument() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (file: File) => {
      // File zu FormData
      const formData = new FormData();
      formData.append('file', file);
      return fetch('/api/v1/documents/', {
        method: 'POST',
        body: formData,
        headers: {
          Authorization: `Bearer ${localStorage.getItem('token')}`,
        },
      }).then((res) => res.json());
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents'] });
    },
  });
}

export function useSearchDocuments() {
  const [query, setQuery] = useState('');

  const { data, isLoading } = useQuery({
    queryKey: ['documents', 'search', query],
    queryFn: () => client.searchDocuments(query),
    enabled: query.length > 2,
  });

  return {
    query,
    setQuery,
    results: data?.items ?? [],
    isLoading,
  };
}

// Beispiel-Komponente
function DocumentUploader() {
  const upload = useUploadDocument();
  const [files, setFiles] = useState<File[]>([]);

  const handleUpload = async () => {
    for (const file of files) {
      await upload.mutateAsync(file);
    }
    setFiles([]);
  };

  return (
    <div>
      <input
        type="file"
        multiple
        onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
      />
      <button onClick={handleUpload} disabled={upload.isPending}>
        {upload.isPending ? 'Lädt hoch...' : 'Hochladen'}
      </button>
    </div>
  );
}
```

---

## cURL Beispiele

### Authentifizierung

```bash
# Login und Token speichern
TOKEN=$(curl -s -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=user@example.com&password=password" | jq -r '.access_token')

echo "Token: $TOKEN"

# Token in Variable für weitere Requests
export AUTH_HEADER="Authorization: Bearer $TOKEN"
```

### Health Check

```bash
curl -s "http://localhost:8000/api/v1/health" | jq
```

### Dokument-Operationen

```bash
# Dokument hochladen
curl -X POST "http://localhost:8000/api/v1/documents/" \
  -H "$AUTH_HEADER" \
  -F "file=@rechnung.pdf" \
  -F "ocr_backend=deepseek" | jq

# Dokument abrufen
curl -s "http://localhost:8000/api/v1/documents/{document_id}" \
  -H "$AUTH_HEADER" | jq

# Dokumente auflisten
curl -s "http://localhost:8000/api/v1/documents/?limit=10&status=completed" \
  -H "$AUTH_HEADER" | jq

# Dokument suchen
curl -s "http://localhost:8000/api/v1/documents/search?q=Rechnung%202025" \
  -H "$AUTH_HEADER" | jq

# Dokument löschen
curl -X DELETE "http://localhost:8000/api/v1/documents/{document_id}" \
  -H "$AUTH_HEADER"

# Dokument herunterladen
curl -o "download.pdf" "http://localhost:8000/api/v1/documents/{document_id}/download" \
  -H "$AUTH_HEADER"
```

### OCR-Operationen

```bash
# OCR-Status
curl -s "http://localhost:8000/api/v1/ocr/{document_id}/status" \
  -H "$AUTH_HEADER" | jq

# OCR erneut starten
curl -X POST "http://localhost:8000/api/v1/ocr/{document_id}/reprocess" \
  -H "$AUTH_HEADER" \
  -H "Content-Type: application/json" \
  -d '{"backend": "deepseek"}' | jq
```

### Batch-Operationen (Shell-Script)

```bash
#!/bin/bash
# batch_upload.sh - Lädt alle PDFs in einem Ordner hoch

FOLDER="$1"
API_URL="http://localhost:8000"
TOKEN="$2"

if [ -z "$FOLDER" ] || [ -z "$TOKEN" ]; then
    echo "Usage: $0 <folder> <token>"
    exit 1
fi

for file in "$FOLDER"/*.pdf; do
    echo "Uploading: $file"
    curl -X POST "$API_URL/api/v1/documents/" \
        -H "Authorization: Bearer $TOKEN" \
        -F "file=@$file" \
        -F "ocr_backend=auto" | jq -r '.id'
done
```

---

## PowerShell Beispiele

```powershell
# Ablage-System PowerShell Client

$BaseUrl = "http://localhost:8000"

function Connect-AblageSystem {
    param(
        [string]$Email,
        [string]$Password
    )

    $body = @{
        username = $Email
        password = $Password
    }

    $response = Invoke-RestMethod -Uri "$BaseUrl/api/v1/auth/login" `
        -Method Post `
        -ContentType "application/x-www-form-urlencoded" `
        -Body $body

    $script:Token = $response.access_token
    Write-Host "Angemeldet als $Email"
}

function Get-AblageHeaders {
    @{
        Authorization = "Bearer $script:Token"
    }
}

function Get-AblageHealth {
    Invoke-RestMethod -Uri "$BaseUrl/api/v1/health" -Method Get
}

function Upload-AblageDocument {
    param(
        [string]$FilePath,
        [string]$OcrBackend = "auto"
    )

    $form = @{
        file = Get-Item -Path $FilePath
        ocr_backend = $OcrBackend
    }

    Invoke-RestMethod -Uri "$BaseUrl/api/v1/documents/" `
        -Method Post `
        -Headers (Get-AblageHeaders) `
        -Form $form
}

function Get-AblageDocument {
    param([string]$DocumentId)

    Invoke-RestMethod -Uri "$BaseUrl/api/v1/documents/$DocumentId" `
        -Method Get `
        -Headers (Get-AblageHeaders)
}

function Get-AblageDocuments {
    param(
        [string]$Status,
        [int]$Limit = 50
    )

    $params = @{ limit = $Limit }
    if ($Status) { $params.status = $Status }

    Invoke-RestMethod -Uri "$BaseUrl/api/v1/documents/" `
        -Method Get `
        -Headers (Get-AblageHeaders) `
        -Body $params
}

function Search-AblageDocuments {
    param(
        [string]$Query,
        [int]$Limit = 20
    )

    Invoke-RestMethod -Uri "$BaseUrl/api/v1/documents/search" `
        -Method Get `
        -Headers (Get-AblageHeaders) `
        -Body @{ q = $Query; limit = $Limit }
}

function Wait-AblageProcessing {
    param(
        [string]$DocumentId,
        [int]$TimeoutSeconds = 300
    )

    $start = Get-Date

    while ((Get-Date) - $start -lt [TimeSpan]::FromSeconds($TimeoutSeconds)) {
        $doc = Get-AblageDocument -DocumentId $DocumentId

        if ($doc.status -in @("completed", "failed")) {
            return $doc
        }

        Start-Sleep -Seconds 2
    }

    throw "Timeout: Dokument nicht innerhalb von $TimeoutSeconds Sekunden verarbeitet"
}

# === Verwendung ===

# Anmelden
Connect-AblageSystem -Email "user@example.com" -Password "password"

# Health Check
Get-AblageHealth

# Dokument hochladen
$doc = Upload-AblageDocument -FilePath ".\rechnung.pdf" -OcrBackend "deepseek"
Write-Host "Dokument ID: $($doc.id)"

# Auf Verarbeitung warten
$processed = Wait-AblageProcessing -DocumentId $doc.id
Write-Host "Status: $($processed.status)"
Write-Host "Text: $($processed.extracted_text.Substring(0, 200))..."

# Suchen
$results = Search-AblageDocuments -Query "Rechnung 2025"
Write-Host "Gefunden: $($results.total) Dokumente"
```

---

## Fehlerbehandlung

### Python

```python
import httpx

try:
    doc = client.upload_document(Path("dokument.pdf"))
except httpx.HTTPStatusError as e:
    if e.response.status_code == 401:
        print("Nicht authentifiziert - bitte erneut anmelden")
    elif e.response.status_code == 413:
        print("Datei zu groß (max. 50 MB)")
    elif e.response.status_code == 415:
        print("Nicht unterstützter Dateityp")
    elif e.response.status_code == 429:
        print("Rate-Limit erreicht - bitte warten")
    else:
        print(f"API-Fehler: {e.response.status_code}")
        print(e.response.json())
except httpx.ConnectError:
    print("Verbindung zum Server fehlgeschlagen")
```

### TypeScript

```typescript
try {
  const doc = await client.uploadDocument('./dokument.pdf');
} catch (error) {
  if (axios.isAxiosError(error)) {
    switch (error.response?.status) {
      case 401:
        console.error('Nicht authentifiziert');
        break;
      case 413:
        console.error('Datei zu groß');
        break;
      case 415:
        console.error('Dateityp nicht unterstützt');
        break;
      case 429:
        console.error('Rate-Limit erreicht');
        break;
      default:
        console.error(`API-Fehler: ${error.response?.status}`);
    }
  }
}
```

---

## Rate Limits

| Endpunkt | Limit |
|----------|-------|
| Login | 5/15min pro IP |
| Upload | 100/h pro User |
| API (allgemein) | 1000/min pro User |
| OCR-Verarbeitung | 10/h pro User |

Bei Überschreitung: HTTP 429 mit `Retry-After` Header.

---

*Letzte Aktualisierung: Januar 2025*
