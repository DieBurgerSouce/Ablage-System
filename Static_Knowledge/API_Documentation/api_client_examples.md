# API Client Examples
**Ablage-System - Praktische Client-Beispiele**

Version: 1.0
Last Updated: 2025-01-23
API Version: v1
Status: PRODUCTION

---

## Executive Summary

Practical code examples for using the Ablage-System API in Python, JavaScript/TypeScript, cURL, and other languages.

**Languages Covered:**
- 🐍 Python (requests, httpx)
- 🟨 JavaScript/TypeScript (fetch, axios)
- 💻 cURL (command line)
- 🦀 Rust (reqwest)
- ☕ Java (HttpClient)

---

## Table of Contents

1. [Python Examples](#python-examples)
2. [JavaScript/TypeScript Examples](#javascripttypescript-examples)
3. [cURL Examples](#curl-examples)
4. [Rust Examples](#rust-examples)
5. [Java Examples](#java-examples)

---

## Python Examples

### Setup

```bash
pip install requests python-dotenv
```

### Basic Client Class

```python
# ablage_client.py

import requests
from typing import Optional, Dict, List, BinaryIO
from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

class AblageClient:
    """Client für Ablage-System API."""

    def __init__(
        self,
        base_url: str = "https://api.ablage.local",
        api_version: str = "v1"
    ):
        self.base_url = base_url
        self.api_version = api_version
        self.session = requests.Session()
        self.access_token: Optional[str] = None

    @property
    def api_url(self) -> str:
        """Vollständige API-URL."""
        return f"{self.base_url}/api/{self.api_version}"

    def login(self, username: str, password: str) -> Dict:
        """Benutzer anmelden."""
        response = self.session.post(
            f"{self.api_url}/auth/login",
            json={"username": username, "password": password}
        )
        response.raise_for_status()

        data = response.json()
        self.access_token = data["access_token"]

        # Set authorization header für zukünftige Requests
        self.session.headers.update({
            "Authorization": f"Bearer {self.access_token}"
        })

        return data

    def logout(self):
        """Benutzer abmelden."""
        response = self.session.post(f"{self.api_url}/auth/logout")
        response.raise_for_status()

        self.access_token = None
        self.session.headers.pop("Authorization", None)

    def get_current_user(self) -> Dict:
        """Aktuellen Benutzer abrufen."""
        response = self.session.get(f"{self.api_url}/auth/me")
        response.raise_for_status()
        return response.json()

    def list_documents(
        self,
        page: int = 1,
        per_page: int = 20,
        tag: Optional[str] = None,
        status: Optional[str] = None
    ) -> Dict:
        """Dokumente auflisten."""
        params = {
            "page": page,
            "per_page": per_page
        }
        if tag:
            params["tag"] = tag
        if status:
            params["status"] = status

        response = self.session.get(
            f"{self.api_url}/documents",
            params=params
        )
        response.raise_for_status()
        return response.json()

    def upload_document(
        self,
        file_path: Path,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict] = None
    ) -> Dict:
        """Dokument hochladen."""
        with open(file_path, 'rb') as f:
            files = {
                'file': (file_path.name, f, 'application/octet-stream')
            }

            data = {}
            if tags:
                data['tags'] = ','.join(tags)
            if metadata:
                import json
                data['metadata'] = json.dumps(metadata)

            response = self.session.post(
                f"{self.api_url}/documents",
                files=files,
                data=data
            )
            response.raise_for_status()
            return response.json()

    def get_document(self, document_id: str) -> Dict:
        """Dokument abrufen."""
        response = self.session.get(f"{self.api_url}/documents/{document_id}")
        response.raise_for_status()
        return response.json()

    def download_document(self, document_id: str, output_path: Path):
        """Dokument herunterladen."""
        response = self.session.get(
            f"{self.api_url}/documents/{document_id}/download",
            stream=True
        )
        response.raise_for_status()

        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

    def start_ocr(
        self,
        document_id: str,
        backend: str = "deepseek",
        force_reprocess: bool = False
    ) -> Dict:
        """OCR-Verarbeitung starten."""
        response = self.session.post(
            f"{self.api_url}/documents/{document_id}/ocr",
            json={
                "backend": backend,
                "force_reprocess": force_reprocess
            }
        )
        response.raise_for_status()
        return response.json()

    def get_ocr_status(self, job_id: str) -> Dict:
        """OCR-Job-Status abrufen."""
        response = self.session.get(f"{self.api_url}/ocr/status/{job_id}")
        response.raise_for_status()
        return response.json()

    def search_documents(
        self,
        query: str,
        tag: Optional[str] = None,
        page: int = 1,
        per_page: int = 20
    ) -> Dict:
        """Dokumente durchsuchen."""
        params = {
            "q": query,
            "page": page,
            "per_page": per_page
        }
        if tag:
            params["tag"] = tag

        response = self.session.get(
            f"{self.api_url}/documents/search",
            params=params
        )
        response.raise_for_status()
        return response.json()

    def update_document(
        self,
        document_id: str,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict] = None
    ) -> Dict:
        """Dokument aktualisieren."""
        data = {}
        if tags is not None:
            data["tags"] = tags
        if metadata is not None:
            data["metadata"] = metadata

        response = self.session.patch(
            f"{self.api_url}/documents/{document_id}",
            json=data
        )
        response.raise_for_status()
        return response.json()

    def delete_document(self, document_id: str):
        """Dokument löschen."""
        response = self.session.delete(f"{self.api_url}/documents/{document_id}")
        response.raise_for_status()

    def health_check(self) -> Dict:
        """System-Gesundheitsprüfung."""
        response = self.session.get(f"{self.api_url}/health")
        response.raise_for_status()
        return response.json()
```

### Usage Examples

```python
# example.py

from ablage_client import AblageClient
from pathlib import Path
import time

def main():
    # Initialize client
    client = AblageClient(base_url="https://api.ablage.local")

    # Login
    print("Login...")
    user_data = client.login(
        username="user@example.com",
        password="SecurePassword123"
    )
    print(f"Logged in as: {user_data['user']['name']}")

    # Get current user
    user = client.get_current_user()
    print(f"Storage used: {user['storage_used_bytes'] / 1024**3:.2f} GB")

    # Upload document
    print("\nUploading document...")
    file_path = Path("rechnung.pdf")
    document = client.upload_document(
        file_path=file_path,
        tags=["rechnung", "2025"],
        metadata={
            "customer": "Firma GmbH",
            "invoice_number": "2025-001"
        }
    )
    doc_id = document["id"]
    print(f"Document uploaded: {doc_id}")

    # Start OCR
    print("\nStarting OCR...")
    ocr_job = client.start_ocr(document_id=doc_id, backend="deepseek")
    job_id = ocr_job["job_id"]
    print(f"OCR job started: {job_id}")

    # Poll OCR status
    while True:
        status = client.get_ocr_status(job_id)
        print(f"OCR status: {status['status']} ({status.get('progress', 0)}%)")

        if status["status"] == "completed":
            print(f"OCR completed in {status['processing_time_ms']}ms")
            print(f"Confidence: {status['result']['confidence']}")
            break
        elif status["status"] == "failed":
            print(f"OCR failed: {status['error']['message']}")
            break

        time.sleep(1)

    # Get document with extracted text
    doc = client.get_document(doc_id)
    print(f"\nExtracted text preview:")
    print(doc["extracted_text"][:200] + "...")

    # Search documents
    print("\nSearching for 'Rechnung'...")
    results = client.search_documents(query="Rechnung", tag="2025")
    print(f"Found {results['pagination']['total']} documents")

    for result in results["data"]:
        print(f"  - {result['filename']} (score: {result['relevance_score']})")

    # Update document
    print("\nUpdating document tags...")
    client.update_document(
        document_id=doc_id,
        tags=["rechnung", "2025", "bezahlt"]
    )

    # Download document
    print("\nDownloading document...")
    client.download_document(doc_id, Path("downloaded.pdf"))
    print("Document downloaded")

    # List all documents
    print("\nListing documents...")
    documents = client.list_documents(per_page=10)
    print(f"Total documents: {documents['pagination']['total']}")

    # Logout
    print("\nLogging out...")
    client.logout()
    print("Logged out successfully")

if __name__ == "__main__":
    main()
```

### Async Client (httpx)

```python
# async_ablage_client.py

import httpx
from typing import Optional, Dict, List
from pathlib import Path

class AsyncAblageClient:
    """Asynchroner Client für Ablage-System API."""

    def __init__(self, base_url: str = "https://api.ablage.local"):
        self.base_url = base_url
        self.client = httpx.AsyncClient()
        self.access_token: Optional[str] = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.client.aclose()

    async def login(self, username: str, password: str) -> Dict:
        """Benutzer anmelden."""
        response = await self.client.post(
            f"{self.base_url}/api/v1/auth/login",
            json={"username": username, "password": password}
        )
        response.raise_for_status()

        data = response.json()
        self.access_token = data["access_token"]
        self.client.headers.update({
            "Authorization": f"Bearer {self.access_token}"
        })

        return data

    async def upload_document(
        self,
        file_path: Path,
        tags: Optional[List[str]] = None
    ) -> Dict:
        """Dokument hochladen."""
        with open(file_path, 'rb') as f:
            files = {'file': (file_path.name, f)}
            data = {}
            if tags:
                data['tags'] = ','.join(tags)

            response = await self.client.post(
                f"{self.base_url}/api/v1/documents",
                files=files,
                data=data
            )
            response.raise_for_status()
            return response.json()

    # ... other async methods

# Usage
async def main():
    async with AsyncAblageClient() as client:
        await client.login("user@example.com", "password")
        doc = await client.upload_document(Path("file.pdf"), tags=["test"])
        print(f"Uploaded: {doc['id']}")

import asyncio
asyncio.run(main())
```

---

## JavaScript/TypeScript Examples

### Basic Client Class

```typescript
// ablageClient.ts

interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: {
    id: string;
    email: string;
    name: string;
  };
}

interface Document {
  id: string;
  filename: string;
  file_size_bytes: number;
  status: string;
  tags: string[];
  created_at: string;
}

interface OCRJob {
  job_id: string;
  document_id: string;
  status: string;
  backend: string;
}

class AblageClient {
  private baseUrl: string;
  private accessToken: string | null = null;

  constructor(baseUrl: string = 'https://api.ablage.local') {
    this.baseUrl = baseUrl;
  }

  private get apiUrl(): string {
    return `${this.baseUrl}/api/v1`;
  }

  private get headers(): HeadersInit {
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
    };

    if (this.accessToken) {
      headers['Authorization'] = `Bearer ${this.accessToken}`;
    }

    return headers;
  }

  async login(username: string, password: string): Promise<LoginResponse> {
    const response = await fetch(`${this.apiUrl}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });

    if (!response.ok) {
      throw new Error(`Login failed: ${response.statusText}`);
    }

    const data = await response.json();
    this.accessToken = data.access_token;
    return data;
  }

  async logout(): Promise<void> {
    await fetch(`${this.apiUrl}/auth/logout`, {
      method: 'POST',
      headers: this.headers,
    });

    this.accessToken = null;
  }

  async listDocuments(
    page: number = 1,
    perPage: number = 20,
    tag?: string
  ): Promise<{ data: Document[]; pagination: any }> {
    const params = new URLSearchParams({
      page: page.toString(),
      per_page: perPage.toString(),
    });

    if (tag) {
      params.append('tag', tag);
    }

    const response = await fetch(`${this.apiUrl}/documents?${params}`, {
      headers: this.headers,
    });

    if (!response.ok) {
      throw new Error(`Failed to list documents: ${response.statusText}`);
    }

    return response.json();
  }

  async uploadDocument(
    file: File,
    tags?: string[],
    metadata?: Record<string, any>
  ): Promise<Document> {
    const formData = new FormData();
    formData.append('file', file);

    if (tags && tags.length > 0) {
      formData.append('tags', tags.join(','));
    }

    if (metadata) {
      formData.append('metadata', JSON.stringify(metadata));
    }

    const headers = { ...this.headers };
    delete headers['Content-Type']; // Let browser set multipart boundary

    const response = await fetch(`${this.apiUrl}/documents`, {
      method: 'POST',
      headers,
      body: formData,
    });

    if (!response.ok) {
      throw new Error(`Failed to upload document: ${response.statusText}`);
    }

    return response.json();
  }

  async getDocument(documentId: string): Promise<Document> {
    const response = await fetch(`${this.apiUrl}/documents/${documentId}`, {
      headers: this.headers,
    });

    if (!response.ok) {
      throw new Error(`Failed to get document: ${response.statusText}`);
    }

    return response.json();
  }

  async downloadDocument(documentId: string): Promise<Blob> {
    const response = await fetch(
      `${this.apiUrl}/documents/${documentId}/download`,
      { headers: this.headers }
    );

    if (!response.ok) {
      throw new Error(`Failed to download document: ${response.statusText}`);
    }

    return response.blob();
  }

  async startOCR(
    documentId: string,
    backend: string = 'deepseek'
  ): Promise<OCRJob> {
    const response = await fetch(`${this.apiUrl}/documents/${documentId}/ocr`, {
      method: 'POST',
      headers: this.headers,
      body: JSON.stringify({ backend }),
    });

    if (!response.ok) {
      throw new Error(`Failed to start OCR: ${response.statusText}`);
    }

    return response.json();
  }

  async getOCRStatus(jobId: string): Promise<any> {
    const response = await fetch(`${this.apiUrl}/ocr/status/${jobId}`, {
      headers: this.headers,
    });

    if (!response.ok) {
      throw new Error(`Failed to get OCR status: ${response.statusText}`);
    }

    return response.json();
  }

  async searchDocuments(
    query: string,
    tag?: string,
    page: number = 1
  ): Promise<{ data: Document[]; pagination: any }> {
    const params = new URLSearchParams({
      q: query,
      page: page.toString(),
    });

    if (tag) {
      params.append('tag', tag);
    }

    const response = await fetch(`${this.apiUrl}/documents/search?${params}`, {
      headers: this.headers,
    });

    if (!response.ok) {
      throw new Error(`Failed to search documents: ${response.statusText}`);
    }

    return response.json();
  }
}

export default AblageClient;
```

### Usage Example

```typescript
// example.ts

import AblageClient from './ablageClient';

async function main() {
  const client = new AblageClient('https://api.ablage.local');

  try {
    // Login
    console.log('Logging in...');
    const loginData = await client.login('user@example.com', 'SecurePassword123');
    console.log(`Logged in as: ${loginData.user.name}`);

    // Upload document
    console.log('\nUploading document...');
    const fileInput = document.querySelector('#fileInput') as HTMLInputElement;
    const file = fileInput.files?.[0];

    if (file) {
      const document = await client.uploadDocument(
        file,
        ['rechnung', '2025'],
        { customer: 'Firma GmbH' }
      );
      console.log(`Document uploaded: ${document.id}`);

      // Start OCR
      console.log('\nStarting OCR...');
      const ocrJob = await client.startOCR(document.id, 'deepseek');
      console.log(`OCR job started: ${ocrJob.job_id}`);

      // Poll OCR status
      while (true) {
        const status = await client.getOCRStatus(ocrJob.job_id);
        console.log(`OCR status: ${status.status} (${status.progress || 0}%)`);

        if (status.status === 'completed') {
          console.log('OCR completed!');
          break;
        } else if (status.status === 'failed') {
          console.error(`OCR failed: ${status.error.message}`);
          break;
        }

        await new Promise(resolve => setTimeout(resolve, 1000));
      }

      // Get document with extracted text
      const doc = await client.getDocument(document.id);
      console.log('\nExtracted text preview:');
      console.log(doc.extracted_text?.substring(0, 200) + '...');
    }

    // Search documents
    console.log('\nSearching for "Rechnung"...');
    const results = await client.searchDocuments('Rechnung', '2025');
    console.log(`Found ${results.pagination.total} documents`);

    // Logout
    console.log('\nLogging out...');
    await client.logout();
    console.log('Logged out successfully');

  } catch (error) {
    console.error('Error:', error);
  }
}

main();
```

---

## cURL Examples

### Authentication

```bash
# Login
curl -X POST https://api.ablage.local/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "user@example.com",
    "password": "SecurePassword123"
  }'

# Response: Save access_token
# export TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

# Get current user
curl https://api.ablage.local/api/v1/auth/me \
  -H "Authorization: Bearer $TOKEN"

# Logout
curl -X POST https://api.ablage.local/api/v1/auth/logout \
  -H "Authorization: Bearer $TOKEN"
```

### Document Operations

```bash
# List documents
curl https://api.ablage.local/api/v1/documents?page=1&per_page=20 \
  -H "Authorization: Bearer $TOKEN"

# Upload document
curl -X POST https://api.ablage.local/api/v1/documents \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@rechnung.pdf" \
  -F "tags=rechnung,2025" \
  -F 'metadata={"customer":"Firma GmbH"}'

# Get document
curl https://api.ablage.local/api/v1/documents/doc_123 \
  -H "Authorization: Bearer $TOKEN"

# Download document
curl https://api.ablage.local/api/v1/documents/doc_123/download \
  -H "Authorization: Bearer $TOKEN" \
  -O -J  # Save with original filename

# Update document
curl -X PATCH https://api.ablage.local/api/v1/documents/doc_123 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tags": ["rechnung", "2025", "bezahlt"]
  }'

# Delete document
curl -X DELETE https://api.ablage.local/api/v1/documents/doc_123 \
  -H "Authorization: Bearer $TOKEN"
```

### OCR Operations

```bash
# Start OCR
curl -X POST https://api.ablage.local/api/v1/documents/doc_123/ocr \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "backend": "deepseek",
    "force_reprocess": false
  }'

# Get OCR status
curl https://api.ablage.local/api/v1/ocr/status/job_456 \
  -H "Authorization: Bearer $TOKEN"

# List OCR backends
curl https://api.ablage.local/api/v1/ocr/backends \
  -H "Authorization: Bearer $TOKEN"
```

### Search

```bash
# Search documents
curl "https://api.ablage.local/api/v1/documents/search?q=Rechnung&tag=2025" \
  -H "Authorization: Bearer $TOKEN"
```

### Health Check

```bash
# Check API health
curl https://api.ablage.local/api/v1/health
```

---

## Rust Examples

```rust
// main.rs

use reqwest::{Client, multipart};
use serde::{Deserialize, Serialize};
use std::path::Path;

#[derive(Debug, Serialize)]
struct LoginRequest {
    username: String,
    password: String,
}

#[derive(Debug, Deserialize)]
struct LoginResponse {
    access_token: String,
    token_type: String,
    user: User,
}

#[derive(Debug, Deserialize)]
struct User {
    id: String,
    email: String,
    name: String,
}

#[derive(Debug, Deserialize)]
struct Document {
    id: String,
    filename: String,
    status: String,
    tags: Vec<String>,
}

struct AblageClient {
    base_url: String,
    client: Client,
    access_token: Option<String>,
}

impl AblageClient {
    fn new(base_url: &str) -> Self {
        Self {
            base_url: base_url.to_string(),
            client: Client::new(),
            access_token: None,
        }
    }

    async fn login(&mut self, username: &str, password: &str) -> Result<LoginResponse, Box<dyn std::error::Error>> {
        let url = format!("{}/api/v1/auth/login", self.base_url);

        let response = self.client
            .post(&url)
            .json(&LoginRequest {
                username: username.to_string(),
                password: password.to_string(),
            })
            .send()
            .await?;

        let data: LoginResponse = response.json().await?;
        self.access_token = Some(data.access_token.clone());

        Ok(data)
    }

    async fn upload_document(&self, file_path: &Path, tags: Vec<String>) -> Result<Document, Box<dyn std::error::Error>> {
        let url = format!("{}/api/v1/documents", self.base_url);

        let file = tokio::fs::read(file_path).await?;
        let filename = file_path.file_name().unwrap().to_str().unwrap();

        let form = multipart::Form::new()
            .part("file", multipart::Part::bytes(file).file_name(filename.to_string()))
            .text("tags", tags.join(","));

        let response = self.client
            .post(&url)
            .header("Authorization", format!("Bearer {}", self.access_token.as_ref().unwrap()))
            .multipart(form)
            .send()
            .await?;

        Ok(response.json().await?)
    }
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut client = AblageClient::new("https://api.ablage.local");

    // Login
    println!("Logging in...");
    let login_data = client.login("user@example.com", "password").await?;
    println!("Logged in as: {}", login_data.user.name);

    // Upload document
    println!("Uploading document...");
    let doc = client.upload_document(
        Path::new("rechnung.pdf"),
        vec!["rechnung".to_string(), "2025".to_string()]
    ).await?;
    println!("Document uploaded: {}", doc.id);

    Ok(())
}
```

---

## Java Examples

```java
// AblageClient.java

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import com.google.gson.Gson;
import com.google.gson.JsonObject;

public class AblageClient {
    private final String baseUrl;
    private final HttpClient client;
    private final Gson gson;
    private String accessToken;

    public AblageClient(String baseUrl) {
        this.baseUrl = baseUrl;
        this.client = HttpClient.newHttpClient();
        this.gson = new Gson();
    }

    public JsonObject login(String username, String password) throws Exception {
        String url = baseUrl + "/api/v1/auth/login";

        JsonObject body = new JsonObject();
        body.addProperty("username", username);
        body.addProperty("password", password);

        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create(url))
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(gson.toJson(body)))
            .build();

        HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());

        JsonObject data = gson.fromJson(response.body(), JsonObject.class);
        this.accessToken = data.get("access_token").getAsString();

        return data;
    }

    public JsonObject listDocuments(int page, int perPage) throws Exception {
        String url = String.format("%s/api/v1/documents?page=%d&per_page=%d",
            baseUrl, page, perPage);

        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create(url))
            .header("Authorization", "Bearer " + accessToken)
            .GET()
            .build();

        HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
        return gson.fromJson(response.body(), JsonObject.class);
    }

    public static void main(String[] args) throws Exception {
        AblageClient client = new AblageClient("https://api.ablage.local");

        // Login
        System.out.println("Logging in...");
        JsonObject loginData = client.login("user@example.com", "password");
        System.out.println("Logged in as: " + loginData.getAsJsonObject("user").get("name").getAsString());

        // List documents
        System.out.println("\nListing documents...");
        JsonObject docs = client.listDocuments(1, 20);
        System.out.println("Total documents: " + docs.getAsJsonObject("pagination").get("total").getAsInt());
    }
}
```

---

## Related Documents

- [API Overview](api_overview.md)
- [Endpoint Reference](endpoint_reference.md)
- [Authentication Guide](authentication_guide.md)
- [Error Handling Guide](error_handling_guide.md)

---

## Revision History

| Version | Date       | Author   | Changes                        |
|---------|------------|----------|--------------------------------|
| 1.0     | 2025-01-23 | API Team | Initial client examples        |

---

**"Code is like humor. When you have to explain it, it's bad." - Cory House**

💻 **Client Examples Complete!**
