# API Client SDK Guide

## Inhaltsverzeichnis

1. [Übersicht](#übersicht)
2. [Python SDK](#python-sdk)
3. [TypeScript/JavaScript SDK](#typescriptjavascript-sdk)
4. [Authentication](#authentication)
5. [Error Handling](#error-handling)
6. [Rate Limiting](#rate-limiting)
7. [Retry Logic](#retry-logic)
8. [Pagination](#pagination)
9. [File Uploads](#file-uploads)
10. [Webhooks Integration](#webhooks-integration)
11. [Testing](#testing)
12. [Best Practices](#best-practices)
13. [Troubleshooting](#troubleshooting)
14. [Appendix](#appendix)

---

## Übersicht

### Verfügbare SDKs

Das Ablage System bietet offizielle SDKs für:

- **Python** - Für Backend-Anwendungen, Scripts, Data Pipelines
- **TypeScript/JavaScript** - Für Frontend-Anwendungen, Node.js Backend

### Features

**Alle SDKs bieten:**
- ✅ Type-safe API calls
- ✅ Automatic authentication
- ✅ Error handling mit retry logic
- ✅ Rate limiting
- ✅ File upload support
- ✅ Webhook signature verification
- ✅ Pagination support
- ✅ Async/await support
- ✅ Comprehensive documentation
- ✅ Unit tests

### Installation

**Python**
```bash
pip install ablage-sdk
```

**TypeScript/JavaScript**
```bash
npm install @ablage/sdk
# or
yarn add @ablage/sdk
```

---

## Python SDK

### Installation

```bash
# Install from PyPI
pip install ablage-sdk

# Install with async support
pip install ablage-sdk[async]

# Install development version
pip install git+https://github.com/ablage/python-sdk.git
```

### Quick Start

```python
from ablage_sdk import AblageClient

# Initialize client
client = AblageClient(
    api_key="your_api_key_here",
    base_url="https://api.ablage.example.com"  # Optional
)

# Upload a document
with open("invoice.pdf", "rb") as f:
    document = client.documents.upload(
        file=f,
        filename="invoice.pdf"
    )

print(f"Document uploaded: {document.id}")

# Wait for OCR processing
document = client.documents.wait_for_completion(document.id, timeout=300)

# Get extracted text
print(f"Extracted text: {document.extracted_text}")
```

### Client Initialization

```python
# ablage_sdk/client.py
from typing import Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

class AblageClient:
    """
    Ablage API Client.

    Args:
        api_key: API key for authentication
        base_url: Base URL for API (default: https://api.ablage.example.com)
        timeout: Request timeout in seconds (default: 30)
        max_retries: Maximum number of retries (default: 3)
        verify_ssl: Verify SSL certificates (default: True)
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.ablage.example.com",
        timeout: int = 30,
        max_retries: int = 3,
        verify_ssl: bool = True
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.verify_ssl = verify_ssl

        # Setup session with retry logic
        self.session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "PUT", "PATCH", "DELETE"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # Set default headers
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "User-Agent": f"ablage-python-sdk/{__version__}"
        })

        # Initialize resource clients
        self.documents = DocumentsClient(self)
        self.users = UsersClient(self)
        self.webhooks = WebhooksClient(self)
        self.analytics = AnalyticsClient(self)

    def request(
        self,
        method: str,
        path: str,
        **kwargs
    ) -> requests.Response:
        """
        Make HTTP request to API.

        Args:
            method: HTTP method
            path: API path (will be joined with base_url)
            **kwargs: Additional arguments for requests

        Returns:
            Response object

        Raises:
            AblageAPIError: If request fails
        """
        url = f"{self.base_url}{path}"

        # Set timeout if not provided
        if 'timeout' not in kwargs:
            kwargs['timeout'] = self.timeout

        # Set verify if not provided
        if 'verify' not in kwargs:
            kwargs['verify'] = self.verify_ssl

        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            return response

        except requests.exceptions.HTTPError as e:
            raise self._handle_http_error(e)
        except requests.exceptions.RequestException as e:
            raise AblageAPIError(f"Request failed: {e}")

    def _handle_http_error(self, error: requests.exceptions.HTTPError):
        """Handle HTTP errors and convert to appropriate exceptions."""
        response = error.response
        status_code = response.status_code

        try:
            error_data = response.json()
            message = error_data.get('message', str(error))
            error_code = error_data.get('code')
        except:
            message = str(error)
            error_code = None

        if status_code == 400:
            return AblageValidationError(message, error_code)
        elif status_code == 401:
            return AblageAuthenticationError(message)
        elif status_code == 403:
            return AblagePermissionError(message)
        elif status_code == 404:
            return AblageNotFoundError(message)
        elif status_code == 429:
            return AblageRateLimitError(message)
        elif status_code >= 500:
            return AblageServerError(message, status_code)
        else:
            return AblageAPIError(message, status_code)
```

### Documents Client

```python
# ablage_sdk/resources/documents.py
from typing import Optional, List, BinaryIO, Dict, Any
import time
from pathlib import Path

class DocumentsClient:
    """Client for document operations."""

    def __init__(self, client):
        self.client = client

    def upload(
        self,
        file: BinaryIO,
        filename: str,
        ocr_backend: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Document:
        """
        Upload a document.

        Args:
            file: File object to upload
            filename: Name of the file
            ocr_backend: OCR backend to use (deepseek, got-ocr, surya)
            metadata: Additional metadata

        Returns:
            Document object

        Example:
            >>> with open("invoice.pdf", "rb") as f:
            ...     doc = client.documents.upload(f, "invoice.pdf")
        """
        files = {
            'file': (filename, file)
        }

        data = {}
        if ocr_backend:
            data['ocr_backend'] = ocr_backend
        if metadata:
            data['metadata'] = metadata

        response = self.client.request(
            'POST',
            '/api/v1/documents/upload',
            files=files,
            data=data
        )

        return Document.from_dict(response.json())

    def get(self, document_id: str) -> Document:
        """
        Get document by ID.

        Args:
            document_id: Document ID

        Returns:
            Document object

        Example:
            >>> doc = client.documents.get("doc_abc123")
        """
        response = self.client.request(
            'GET',
            f'/api/v1/documents/{document_id}'
        )

        return Document.from_dict(response.json())

    def list(
        self,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc"
    ) -> PaginatedResponse[Document]:
        """
        List documents.

        Args:
            page: Page number (starting at 1)
            page_size: Number of items per page
            status: Filter by status (pending, processing, completed, failed)
            sort_by: Field to sort by
            sort_order: Sort order (asc, desc)

        Returns:
            Paginated response with documents

        Example:
            >>> response = client.documents.list(page=1, page_size=20)
            >>> for doc in response.items:
            ...     print(doc.filename)
        """
        params = {
            'page': page,
            'page_size': page_size,
            'sort_by': sort_by,
            'sort_order': sort_order
        }

        if status:
            params['status'] = status

        response = self.client.request(
            'GET',
            '/api/v1/documents',
            params=params
        )

        data = response.json()
        return PaginatedResponse(
            items=[Document.from_dict(d) for d in data['items']],
            total=data['total'],
            page=data['page'],
            page_size=data['page_size'],
            total_pages=data['total_pages']
        )

    def update(
        self,
        document_id: str,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None
    ) -> Document:
        """
        Update document metadata.

        Args:
            document_id: Document ID
            metadata: Metadata to update
            tags: Tags to set

        Returns:
            Updated document

        Example:
            >>> doc = client.documents.update(
            ...     "doc_abc123",
            ...     metadata={"invoice_number": "12345"},
            ...     tags=["invoice", "paid"]
            ... )
        """
        data = {}
        if metadata is not None:
            data['metadata'] = metadata
        if tags is not None:
            data['tags'] = tags

        response = self.client.request(
            'PATCH',
            f'/api/v1/documents/{document_id}',
            json=data
        )

        return Document.from_dict(response.json())

    def delete(self, document_id: str) -> None:
        """
        Delete a document.

        Args:
            document_id: Document ID

        Example:
            >>> client.documents.delete("doc_abc123")
        """
        self.client.request(
            'DELETE',
            f'/api/v1/documents/{document_id}'
        )

    def download(self, document_id: str, output_path: Optional[str] = None) -> bytes:
        """
        Download document file.

        Args:
            document_id: Document ID
            output_path: Optional path to save file

        Returns:
            File content as bytes

        Example:
            >>> # Download to file
            >>> client.documents.download("doc_abc123", "invoice.pdf")
            >>>
            >>> # Get content as bytes
            >>> content = client.documents.download("doc_abc123")
        """
        response = self.client.request(
            'GET',
            f'/api/v1/documents/{document_id}/download'
        )

        content = response.content

        if output_path:
            with open(output_path, 'wb') as f:
                f.write(content)

        return content

    def wait_for_completion(
        self,
        document_id: str,
        timeout: int = 300,
        poll_interval: int = 2
    ) -> Document:
        """
        Wait for document processing to complete.

        Args:
            document_id: Document ID
            timeout: Maximum time to wait in seconds
            poll_interval: Time between polls in seconds

        Returns:
            Completed document

        Raises:
            TimeoutError: If processing doesn't complete within timeout
            AblageAPIError: If processing fails

        Example:
            >>> doc = client.documents.upload(file, "invoice.pdf")
            >>> doc = client.documents.wait_for_completion(doc.id, timeout=300)
            >>> print(doc.extracted_text)
        """
        start_time = time.time()

        while True:
            doc = self.get(document_id)

            if doc.status == "completed":
                return doc
            elif doc.status == "failed":
                raise AblageAPIError(f"Document processing failed: {doc.error_message}")

            elapsed = time.time() - start_time
            if elapsed >= timeout:
                raise TimeoutError(f"Document processing timed out after {timeout} seconds")

            time.sleep(poll_interval)

    def get_extracted_text(self, document_id: str) -> str:
        """
        Get extracted text from document.

        Args:
            document_id: Document ID

        Returns:
            Extracted text

        Example:
            >>> text = client.documents.get_extracted_text("doc_abc123")
        """
        response = self.client.request(
            'GET',
            f'/api/v1/documents/{document_id}/extracted-text'
        )

        return response.json()['text']

    def reprocess(
        self,
        document_id: str,
        ocr_backend: Optional[str] = None
    ) -> Document:
        """
        Reprocess document with OCR.

        Args:
            document_id: Document ID
            ocr_backend: OCR backend to use

        Returns:
            Updated document

        Example:
            >>> doc = client.documents.reprocess("doc_abc123", ocr_backend="deepseek")
        """
        data = {}
        if ocr_backend:
            data['ocr_backend'] = ocr_backend

        response = self.client.request(
            'POST',
            f'/api/v1/documents/{document_id}/reprocess',
            json=data
        )

        return Document.from_dict(response.json())
```

### Models

```python
# ablage_sdk/models.py
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from datetime import datetime

@dataclass
class Document:
    """Document model."""

    id: str
    filename: str
    status: str  # pending, processing, completed, failed
    user_id: str
    size: int
    mime_type: str
    ocr_backend: Optional[str] = None
    extracted_text: Optional[str] = None
    confidence_score: Optional[float] = None
    error_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    @classmethod
    def from_dict(cls, data: dict) -> 'Document':
        """Create Document from API response."""
        # Parse datetime fields
        for field in ['created_at', 'updated_at', 'completed_at']:
            if data.get(field):
                data[field] = datetime.fromisoformat(data[field].replace('Z', '+00:00'))

        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        result = {}
        for key, value in self.__dict__.items():
            if isinstance(value, datetime):
                result[key] = value.isoformat()
            else:
                result[key] = value
        return result

@dataclass
class User:
    """User model."""

    id: str
    email: str
    role: str
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_dict(cls, data: dict) -> 'User':
        """Create User from API response."""
        for field in ['created_at', 'updated_at']:
            if data.get(field):
                data[field] = datetime.fromisoformat(data[field].replace('Z', '+00:00'))

        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})

@dataclass
class WebhookSubscription:
    """Webhook subscription model."""

    id: str
    url: str
    event_types: List[str]
    is_active: bool
    secret: Optional[str] = None
    description: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_dict(cls, data: dict) -> 'WebhookSubscription':
        """Create WebhookSubscription from API response."""
        for field in ['created_at', 'updated_at']:
            if data.get(field):
                data[field] = datetime.fromisoformat(data[field].replace('Z', '+00:00'))

        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})

@dataclass
class PaginatedResponse:
    """Paginated response container."""

    items: List[Any]
    total: int
    page: int
    page_size: int
    total_pages: int

    def __iter__(self):
        """Make response iterable."""
        return iter(self.items)

    def __len__(self):
        """Get number of items."""
        return len(self.items)

    def __getitem__(self, index):
        """Get item by index."""
        return self.items[index]
```

### Exceptions

```python
# ablage_sdk/exceptions.py

class AblageError(Exception):
    """Base exception for Ablage SDK."""
    pass

class AblageAPIError(AblageError):
    """General API error."""

    def __init__(self, message: str, status_code: int = None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)

class AblageValidationError(AblageAPIError):
    """Validation error (400)."""

    def __init__(self, message: str, error_code: str = None):
        self.error_code = error_code
        super().__init__(message, 400)

class AblageAuthenticationError(AblageAPIError):
    """Authentication error (401)."""

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, 401)

class AblagePermissionError(AblageAPIError):
    """Permission error (403)."""

    def __init__(self, message: str = "Permission denied"):
        super().__init__(message, 403)

class AblageNotFoundError(AblageAPIError):
    """Resource not found (404)."""

    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, 404)

class AblageRateLimitError(AblageAPIError):
    """Rate limit exceeded (429)."""

    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(message, 429)

class AblageServerError(AblageAPIError):
    """Server error (5xx)."""

    def __init__(self, message: str, status_code: int):
        super().__init__(message, status_code)
```

### Complete Example

```python
# example_usage.py
from ablage_sdk import AblageClient
from ablage_sdk.exceptions import AblageError
import os

# Initialize client
client = AblageClient(
    api_key=os.getenv("ABLAGE_API_KEY"),
    base_url="https://api.ablage.example.com"
)

try:
    # Upload document
    print("Uploading document...")
    with open("invoice.pdf", "rb") as f:
        document = client.documents.upload(
            file=f,
            filename="invoice.pdf",
            ocr_backend="deepseek",
            metadata={"department": "finance"}
        )

    print(f"Document uploaded: {document.id}")
    print(f"Status: {document.status}")

    # Wait for processing
    print("Waiting for OCR processing...")
    document = client.documents.wait_for_completion(
        document.id,
        timeout=300
    )

    print(f"Processing complete!")
    print(f"Confidence score: {document.confidence_score}")
    print(f"Extracted text: {document.extracted_text[:100]}...")

    # Update metadata
    print("Updating metadata...")
    document = client.documents.update(
        document.id,
        metadata={"invoice_number": "INV-2025-001", "amount": 1234.56},
        tags=["invoice", "2025", "finance"]
    )

    # List all documents
    print("\nListing documents...")
    response = client.documents.list(page=1, page_size=10)
    print(f"Total documents: {response.total}")

    for doc in response.items:
        print(f"- {doc.filename} ({doc.status})")

    # Download document
    print("\nDownloading document...")
    client.documents.download(document.id, "invoice_downloaded.pdf")
    print("Download complete!")

except AblageError as e:
    print(f"Error: {e}")
```

---

## TypeScript/JavaScript SDK

### Installation

```bash
# NPM
npm install @ablage/sdk

# Yarn
yarn add @ablage/sdk

# PNPM
pnpm add @ablage/sdk
```

### Quick Start

```typescript
import { AblageClient } from '@ablage/sdk';

// Initialize client
const client = new AblageClient({
  apiKey: process.env.ABLAGE_API_KEY!,
  baseUrl: 'https://api.ablage.example.com'
});

// Upload a document
const file = fs.createReadStream('invoice.pdf');
const document = await client.documents.upload({
  file,
  filename: 'invoice.pdf'
});

console.log(`Document uploaded: ${document.id}`);

// Wait for completion
const completed = await client.documents.waitForCompletion(
  document.id,
  { timeout: 300000 }
);

console.log(`Extracted text: ${completed.extractedText}`);
```

### Client Implementation

```typescript
// src/client.ts
import axios, { AxiosInstance, AxiosRequestConfig } from 'axios';
import axiosRetry from 'axios-retry';

export interface AblageClientConfig {
  apiKey: string;
  baseUrl?: string;
  timeout?: number;
  maxRetries?: number;
}

export class AblageClient {
  private client: AxiosInstance;
  public documents: DocumentsClient;
  public users: UsersClient;
  public webhooks: WebhooksClient;
  public analytics: AnalyticsClient;

  constructor(config: AblageClientConfig) {
    const {
      apiKey,
      baseUrl = 'https://api.ablage.example.com',
      timeout = 30000,
      maxRetries = 3
    } = config;

    // Create axios instance
    this.client = axios.create({
      baseURL: baseUrl,
      timeout,
      headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Content-Type': 'application/json',
        'User-Agent': `ablage-typescript-sdk/${version}`
      }
    });

    // Configure retry logic
    axiosRetry(this.client, {
      retries: maxRetries,
      retryDelay: axiosRetry.exponentialDelay,
      retryCondition: (error) => {
        return axiosRetry.isNetworkOrIdempotentRequestError(error) ||
          error.response?.status === 429 ||
          (error.response?.status ?? 0) >= 500;
      }
    });

    // Add response interceptor for error handling
    this.client.interceptors.response.use(
      (response) => response,
      (error) => {
        throw this.handleError(error);
      }
    );

    // Initialize resource clients
    this.documents = new DocumentsClient(this.client);
    this.users = new UsersClient(this.client);
    this.webhooks = new WebhooksClient(this.client);
    this.analytics = new AnalyticsClient(this.client);
  }

  private handleError(error: any): AblageError {
    if (!error.response) {
      return new AblageError('Network error', 0);
    }

    const { status, data } = error.response;
    const message = data?.message || error.message;
    const errorCode = data?.code;

    switch (status) {
      case 400:
        return new AblageValidationError(message, errorCode);
      case 401:
        return new AblageAuthenticationError(message);
      case 403:
        return new AblagePermissionError(message);
      case 404:
        return new AblageNotFoundError(message);
      case 429:
        return new AblageRateLimitError(message);
      case 500:
      case 502:
      case 503:
      case 504:
        return new AblageServerError(message, status);
      default:
        return new AblageError(message, status);
    }
  }
}
```

### Documents Client

```typescript
// src/resources/documents.ts
import { AxiosInstance } from 'axios';
import FormData from 'form-data';
import { Readable } from 'stream';

export interface UploadOptions {
  file: Readable | Buffer;
  filename: string;
  ocrBackend?: 'deepseek' | 'got-ocr' | 'surya';
  metadata?: Record<string, any>;
}

export interface ListOptions {
  page?: number;
  pageSize?: number;
  status?: 'pending' | 'processing' | 'completed' | 'failed';
  sortBy?: string;
  sortOrder?: 'asc' | 'desc';
}

export interface UpdateOptions {
  metadata?: Record<string, any>;
  tags?: string[];
}

export interface WaitOptions {
  timeout?: number;
  pollInterval?: number;
}

export class DocumentsClient {
  constructor(private client: AxiosInstance) {}

  async upload(options: UploadOptions): Promise<Document> {
    const { file, filename, ocrBackend, metadata } = options;

    const formData = new FormData();
    formData.append('file', file, filename);

    if (ocrBackend) {
      formData.append('ocr_backend', ocrBackend);
    }

    if (metadata) {
      formData.append('metadata', JSON.stringify(metadata));
    }

    const response = await this.client.post(
      '/api/v1/documents/upload',
      formData,
      {
        headers: formData.getHeaders()
      }
    );

    return Document.fromJSON(response.data);
  }

  async get(documentId: string): Promise<Document> {
    const response = await this.client.get(
      `/api/v1/documents/${documentId}`
    );

    return Document.fromJSON(response.data);
  }

  async list(options: ListOptions = {}): Promise<PaginatedResponse<Document>> {
    const {
      page = 1,
      pageSize = 20,
      status,
      sortBy = 'created_at',
      sortOrder = 'desc'
    } = options;

    const params: any = {
      page,
      page_size: pageSize,
      sort_by: sortBy,
      sort_order: sortOrder
    };

    if (status) {
      params.status = status;
    }

    const response = await this.client.get('/api/v1/documents', { params });

    return {
      items: response.data.items.map((d: any) => Document.fromJSON(d)),
      total: response.data.total,
      page: response.data.page,
      pageSize: response.data.page_size,
      totalPages: response.data.total_pages
    };
  }

  async update(
    documentId: string,
    options: UpdateOptions
  ): Promise<Document> {
    const { metadata, tags } = options;

    const data: any = {};
    if (metadata !== undefined) {
      data.metadata = metadata;
    }
    if (tags !== undefined) {
      data.tags = tags;
    }

    const response = await this.client.patch(
      `/api/v1/documents/${documentId}`,
      data
    );

    return Document.fromJSON(response.data);
  }

  async delete(documentId: string): Promise<void> {
    await this.client.delete(`/api/v1/documents/${documentId}`);
  }

  async download(documentId: string): Promise<Buffer> {
    const response = await this.client.get(
      `/api/v1/documents/${documentId}/download`,
      { responseType: 'arraybuffer' }
    );

    return Buffer.from(response.data);
  }

  async waitForCompletion(
    documentId: string,
    options: WaitOptions = {}
  ): Promise<Document> {
    const {
      timeout = 300000, // 5 minutes
      pollInterval = 2000 // 2 seconds
    } = options;

    const startTime = Date.now();

    while (true) {
      const doc = await this.get(documentId);

      if (doc.status === 'completed') {
        return doc;
      } else if (doc.status === 'failed') {
        throw new AblageError(
          `Document processing failed: ${doc.errorMessage}`
        );
      }

      const elapsed = Date.now() - startTime;
      if (elapsed >= timeout) {
        throw new Error(
          `Document processing timed out after ${timeout}ms`
        );
      }

      await new Promise(resolve => setTimeout(resolve, pollInterval));
    }
  }

  async getExtractedText(documentId: string): Promise<string> {
    const response = await this.client.get(
      `/api/v1/documents/${documentId}/extracted-text`
    );

    return response.data.text;
  }

  async reprocess(
    documentId: string,
    ocrBackend?: string
  ): Promise<Document> {
    const data: any = {};
    if (ocrBackend) {
      data.ocr_backend = ocrBackend;
    }

    const response = await this.client.post(
      `/api/v1/documents/${documentId}/reprocess`,
      data
    );

    return Document.fromJSON(response.data);
  }
}
```

### Models

```typescript
// src/models.ts

export class Document {
  constructor(
    public id: string,
    public filename: string,
    public status: 'pending' | 'processing' | 'completed' | 'failed',
    public userId: string,
    public size: number,
    public mimeType: string,
    public ocrBackend?: string,
    public extractedText?: string,
    public confidenceScore?: number,
    public errorMessage?: string,
    public metadata?: Record<string, any>,
    public tags?: string[],
    public createdAt?: Date,
    public updatedAt?: Date,
    public completedAt?: Date
  ) {}

  static fromJSON(data: any): Document {
    return new Document(
      data.id,
      data.filename,
      data.status,
      data.user_id,
      data.size,
      data.mime_type,
      data.ocr_backend,
      data.extracted_text,
      data.confidence_score,
      data.error_message,
      data.metadata,
      data.tags,
      data.created_at ? new Date(data.created_at) : undefined,
      data.updated_at ? new Date(data.updated_at) : undefined,
      data.completed_at ? new Date(data.completed_at) : undefined
    );
  }

  toJSON(): any {
    return {
      id: this.id,
      filename: this.filename,
      status: this.status,
      user_id: this.userId,
      size: this.size,
      mime_type: this.mimeType,
      ocr_backend: this.ocrBackend,
      extracted_text: this.extractedText,
      confidence_score: this.confidenceScore,
      error_message: this.errorMessage,
      metadata: this.metadata,
      tags: this.tags,
      created_at: this.createdAt?.toISOString(),
      updated_at: this.updatedAt?.toISOString(),
      completed_at: this.completedAt?.toISOString()
    };
  }
}

export class User {
  constructor(
    public id: string,
    public email: string,
    public role: string,
    public isActive: boolean,
    public createdAt?: Date,
    public updatedAt?: Date
  ) {}

  static fromJSON(data: any): User {
    return new User(
      data.id,
      data.email,
      data.role,
      data.is_active,
      data.created_at ? new Date(data.created_at) : undefined,
      data.updated_at ? new Date(data.updated_at) : undefined
    );
  }
}

export class WebhookSubscription {
  constructor(
    public id: string,
    public url: string,
    public eventTypes: string[],
    public isActive: boolean,
    public secret?: string,
    public description?: string,
    public headers?: Record<string, string>,
    public createdAt?: Date,
    public updatedAt?: Date
  ) {}

  static fromJSON(data: any): WebhookSubscription {
    return new WebhookSubscription(
      data.id,
      data.url,
      data.event_types,
      data.is_active,
      data.secret,
      data.description,
      data.headers,
      data.created_at ? new Date(data.created_at) : undefined,
      data.updated_at ? new Date(data.updated_at) : undefined
    );
  }
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
}
```

### Exceptions

```typescript
// src/exceptions.ts

export class AblageError extends Error {
  constructor(
    message: string,
    public statusCode?: number
  ) {
    super(message);
    this.name = 'AblageError';
  }
}

export class AblageValidationError extends AblageError {
  constructor(
    message: string,
    public errorCode?: string
  ) {
    super(message, 400);
    this.name = 'AblageValidationError';
  }
}

export class AblageAuthenticationError extends AblageError {
  constructor(message: string = 'Authentication failed') {
    super(message, 401);
    this.name = 'AblageAuthenticationError';
  }
}

export class AblagePermissionError extends AblageError {
  constructor(message: string = 'Permission denied') {
    super(message, 403);
    this.name = 'AblagePermissionError';
  }
}

export class AblageNotFoundError extends AblageError {
  constructor(message: string = 'Resource not found') {
    super(message, 404);
    this.name = 'AblageNotFoundError';
  }
}

export class AblageRateLimitError extends AblageError {
  constructor(message: string = 'Rate limit exceeded') {
    super(message, 429);
    this.name = 'AblageRateLimitError';
  }
}

export class AblageServerError extends AblageError {
  constructor(message: string, statusCode: number) {
    super(message, statusCode);
    this.name = 'AblageServerError';
  }
}
```

### Complete Example

```typescript
// example.ts
import { AblageClient } from '@ablage/sdk';
import fs from 'fs';

async function main() {
  // Initialize client
  const client = new AblageClient({
    apiKey: process.env.ABLAGE_API_KEY!,
    baseUrl: 'https://api.ablage.example.com'
  });

  try {
    // Upload document
    console.log('Uploading document...');
    const file = fs.createReadStream('invoice.pdf');
    const document = await client.documents.upload({
      file,
      filename: 'invoice.pdf',
      ocrBackend: 'deepseek',
      metadata: { department: 'finance' }
    });

    console.log(`Document uploaded: ${document.id}`);
    console.log(`Status: ${document.status}`);

    // Wait for processing
    console.log('Waiting for OCR processing...');
    const completed = await client.documents.waitForCompletion(
      document.id,
      { timeout: 300000 }
    );

    console.log('Processing complete!');
    console.log(`Confidence score: ${completed.confidenceScore}`);
    console.log(`Extracted text: ${completed.extractedText?.substring(0, 100)}...`);

    // Update metadata
    console.log('Updating metadata...');
    await client.documents.update(document.id, {
      metadata: {
        invoice_number: 'INV-2025-001',
        amount: 1234.56
      },
      tags: ['invoice', '2025', 'finance']
    });

    // List documents
    console.log('\nListing documents...');
    const response = await client.documents.list({
      page: 1,
      pageSize: 10
    });

    console.log(`Total documents: ${response.total}`);
    for (const doc of response.items) {
      console.log(`- ${doc.filename} (${doc.status})`);
    }

    // Download document
    console.log('\nDownloading document...');
    const buffer = await client.documents.download(document.id);
    fs.writeFileSync('invoice_downloaded.pdf', buffer);
    console.log('Download complete!');

  } catch (error) {
    console.error('Error:', error);
  }
}

main();
```

---

## Authentication

### API Key Authentication

**Python**
```python
from ablage_sdk import AblageClient

# Initialize with API key
client = AblageClient(api_key="your_api_key_here")

# API key is automatically included in all requests
# as "Authorization: Bearer <api_key>"
```

**TypeScript**
```typescript
import { AblageClient } from '@ablage/sdk';

const client = new AblageClient({
  apiKey: process.env.ABLAGE_API_KEY!
});
```

### Environment Variables

**Python**
```python
import os
from ablage_sdk import AblageClient

# Read from environment
client = AblageClient(
    api_key=os.getenv("ABLAGE_API_KEY"),
    base_url=os.getenv("ABLAGE_BASE_URL", "https://api.ablage.example.com")
)
```

**TypeScript**
```typescript
import { AblageClient } from '@ablage/sdk';

const client = new AblageClient({
  apiKey: process.env.ABLAGE_API_KEY!,
  baseUrl: process.env.ABLAGE_BASE_URL || 'https://api.ablage.example.com'
});
```

### Creating API Keys

```python
# Create API key via API
from ablage_sdk import AblageClient

client = AblageClient(api_key="admin_key")

# Create new API key
api_key = client.api_keys.create(
    name="Production API Key",
    scopes=["documents:read", "documents:write"]
)

print(f"API Key: {api_key.key}")
print(f"Keep this safe! It won't be shown again.")
```

---

## Error Handling

### Exception Hierarchy

```python
# Python
AblageError
├── AblageAPIError
│   ├── AblageValidationError (400)
│   ├── AblageAuthenticationError (401)
│   ├── AblagePermissionError (403)
│   ├── AblageNotFoundError (404)
│   ├── AblageRateLimitError (429)
│   └── AblageServerError (5xx)
```

### Handling Errors

**Python**
```python
from ablage_sdk import AblageClient
from ablage_sdk.exceptions import (
    AblageValidationError,
    AblageAuthenticationError,
    AblageNotFoundError,
    AblageRateLimitError,
    AblageError
)

client = AblageClient(api_key="...")

try:
    document = client.documents.get("doc_123")

except AblageValidationError as e:
    print(f"Validation error: {e.message}")
    print(f"Error code: {e.error_code}")

except AblageAuthenticationError:
    print("Authentication failed. Check your API key.")

except AblageNotFoundError:
    print("Document not found")

except AblageRateLimitError:
    print("Rate limit exceeded. Please wait before retrying.")
    # Implement exponential backoff
    time.sleep(60)

except AblageError as e:
    print(f"API error: {e.message} (status: {e.status_code})")

except Exception as e:
    print(f"Unexpected error: {e}")
```

**TypeScript**
```typescript
import { AblageClient } from '@ablage/sdk';
import {
  AblageValidationError,
  AblageAuthenticationError,
  AblageNotFoundError,
  AblageRateLimitError,
  AblageError
} from '@ablage/sdk/exceptions';

const client = new AblageClient({ apiKey: '...' });

try {
  const document = await client.documents.get('doc_123');

} catch (error) {
  if (error instanceof AblageValidationError) {
    console.log(`Validation error: ${error.message}`);
    console.log(`Error code: ${error.errorCode}`);

  } else if (error instanceof AblageAuthenticationError) {
    console.log('Authentication failed. Check your API key.');

  } else if (error instanceof AblageNotFoundError) {
    console.log('Document not found');

  } else if (error instanceof AblageRateLimitError) {
    console.log('Rate limit exceeded. Please wait before retrying.');
    await new Promise(resolve => setTimeout(resolve, 60000));

  } else if (error instanceof AblageError) {
    console.log(`API error: ${error.message} (status: ${error.statusCode})`);

  } else {
    console.log(`Unexpected error: ${error}`);
  }
}
```

---

## Rate Limiting

### Rate Limit Headers

```http
HTTP/1.1 200 OK
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1642444800
```

### Handling Rate Limits

**Python**
```python
import time
from ablage_sdk.exceptions import AblageRateLimitError

def upload_with_rate_limit_handling(client, files):
    """Upload files with automatic rate limit handling."""
    for file_path in files:
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                with open(file_path, 'rb') as f:
                    doc = client.documents.upload(f, file_path)
                print(f"Uploaded: {file_path}")
                break

            except AblageRateLimitError as e:
                retry_count += 1
                if retry_count >= max_retries:
                    raise

                # Exponential backoff
                wait_time = 2 ** retry_count
                print(f"Rate limited. Waiting {wait_time}s...")
                time.sleep(wait_time)
```

**TypeScript**
```typescript
import { AblageClient, AblageRateLimitError } from '@ablage/sdk';

async function uploadWithRateLimitHandling(
  client: AblageClient,
  files: string[]
) {
  for (const filePath of files) {
    let retryCount = 0;
    const maxRetries = 3;

    while (retryCount < maxRetries) {
      try {
        const file = fs.createReadStream(filePath);
        const doc = await client.documents.upload({
          file,
          filename: path.basename(filePath)
        });

        console.log(`Uploaded: ${filePath}`);
        break;

      } catch (error) {
        if (error instanceof AblageRateLimitError) {
          retryCount++;
          if (retryCount >= maxRetries) {
            throw error;
          }

          // Exponential backoff
          const waitTime = Math.pow(2, retryCount) * 1000;
          console.log(`Rate limited. Waiting ${waitTime}ms...`);
          await new Promise(resolve => setTimeout(resolve, waitTime));

        } else {
          throw error;
        }
      }
    }
  }
}
```

---

## Retry Logic

### Automatic Retries

Both SDKs implement automatic retry logic for:
- Network errors
- Timeouts
- Rate limiting (429)
- Server errors (500, 502, 503, 504)

**Python Configuration**
```python
from ablage_sdk import AblageClient

client = AblageClient(
    api_key="...",
    max_retries=5,  # Maximum retry attempts
    timeout=60  # Request timeout in seconds
)
```

**TypeScript Configuration**
```typescript
import { AblageClient } from '@ablage/sdk';

const client = new AblageClient({
  apiKey: '...',
  maxRetries: 5,  // Maximum retry attempts
  timeout: 60000  // Request timeout in milliseconds
});
```

### Custom Retry Logic

**Python**
```python
from ablage_sdk import AblageClient
from ablage_sdk.exceptions import AblageServerError
import time

def retry_with_exponential_backoff(func, max_retries=5):
    """Execute function with exponential backoff retry."""
    for attempt in range(max_retries):
        try:
            return func()
        except AblageServerError as e:
            if attempt == max_retries - 1:
                raise

            wait_time = (2 ** attempt) + (random.random() * 0.1)
            print(f"Attempt {attempt + 1} failed. Retrying in {wait_time:.2f}s...")
            time.sleep(wait_time)

# Usage
client = AblageClient(api_key="...")

document = retry_with_exponential_backoff(
    lambda: client.documents.get("doc_123")
)
```

---

## Pagination

### Iterating Through Pages

**Python**
```python
from ablage_sdk import AblageClient

client = AblageClient(api_key="...")

# Manual pagination
page = 1
while True:
    response = client.documents.list(page=page, page_size=50)

    for doc in response.items:
        print(f"Document: {doc.filename}")

    if page >= response.total_pages:
        break

    page += 1

# Helper method for all items
def iter_all_documents(client):
    """Iterate through all documents."""
    page = 1
    while True:
        response = client.documents.list(page=page)

        for doc in response.items:
            yield doc

        if page >= response.total_pages:
            break

        page += 1

# Usage
for doc in iter_all_documents(client):
    print(doc.filename)
```

**TypeScript**
```typescript
import { AblageClient } from '@ablage/sdk';

const client = new AblageClient({ apiKey: '...' });

// Manual pagination
let page = 1;
while (true) {
  const response = await client.documents.list({
    page,
    pageSize: 50
  });

  for (const doc of response.items) {
    console.log(`Document: ${doc.filename}`);
  }

  if (page >= response.totalPages) {
    break;
  }

  page++;
}

// Helper function for all items
async function* iterAllDocuments(client: AblageClient) {
  let page = 1;

  while (true) {
    const response = await client.documents.list({ page });

    for (const doc of response.items) {
      yield doc;
    }

    if (page >= response.totalPages) {
      break;
    }

    page++;
  }
}

// Usage
for await (const doc of iterAllDocuments(client)) {
  console.log(doc.filename);
}
```

---

## File Uploads

### Upload from File

**Python**
```python
from ablage_sdk import AblageClient

client = AblageClient(api_key="...")

# Upload from file path
with open("invoice.pdf", "rb") as f:
    doc = client.documents.upload(f, "invoice.pdf")

# Upload with metadata
with open("contract.pdf", "rb") as f:
    doc = client.documents.upload(
        file=f,
        filename="contract.pdf",
        ocr_backend="deepseek",
        metadata={
            "type": "contract",
            "client": "ACME Corp",
            "year": 2025
        }
    )
```

**TypeScript**
```typescript
import { AblageClient } from '@ablage/sdk';
import fs from 'fs';

const client = new AblageClient({ apiKey: '...' });

// Upload from file stream
const file = fs.createReadStream('invoice.pdf');
const doc = await client.documents.upload({
  file,
  filename: 'invoice.pdf'
});

// Upload with metadata
const file2 = fs.createReadStream('contract.pdf');
const doc2 = await client.documents.upload({
  file: file2,
  filename: 'contract.pdf',
  ocrBackend: 'deepseek',
  metadata: {
    type: 'contract',
    client: 'ACME Corp',
    year: 2025
  }
});
```

### Upload from Buffer/Bytes

**Python**
```python
# Upload from bytes
pdf_bytes = b'%PDF-1.4...'  # PDF content
import io

doc = client.documents.upload(
    file=io.BytesIO(pdf_bytes),
    filename="generated.pdf"
)
```

**TypeScript**
```typescript
// Upload from Buffer
const pdfBuffer = Buffer.from('...');  // PDF content

const doc = await client.documents.upload({
  file: pdfBuffer,
  filename: 'generated.pdf'
});
```

### Batch Upload

**Python**
```python
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

def upload_directory(client, directory_path, max_workers=5):
    """Upload all PDFs from a directory."""
    pdf_files = Path(directory_path).glob("*.pdf")

    def upload_file(file_path):
        with open(file_path, "rb") as f:
            doc = client.documents.upload(f, file_path.name)
        return doc

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = executor.map(upload_file, pdf_files)

    return list(results)

# Usage
documents = upload_directory(client, "/path/to/pdfs")
print(f"Uploaded {len(documents)} documents")
```

**TypeScript**
```typescript
import { AblageClient } from '@ablage/sdk';
import fs from 'fs';
import path from 'path';
import { promisify } from 'util';

const readdir = promisify(fs.readdir);

async function uploadDirectory(
  client: AblageClient,
  directoryPath: string,
  concurrency: number = 5
) {
  const files = await readdir(directoryPath);
  const pdfFiles = files.filter(f => f.endsWith('.pdf'));

  const uploadFile = async (filename: string) => {
    const filePath = path.join(directoryPath, filename);
    const file = fs.createReadStream(filePath);

    return client.documents.upload({ file, filename });
  };

  // Upload with concurrency control
  const results = [];
  for (let i = 0; i < pdfFiles.length; i += concurrency) {
    const batch = pdfFiles.slice(i, i + concurrency);
    const batchResults = await Promise.all(batch.map(uploadFile));
    results.push(...batchResults);
  }

  return results;
}

// Usage
const documents = await uploadDirectory(client, '/path/to/pdfs');
console.log(`Uploaded ${documents.length} documents`);
```

---

## Webhooks Integration

### Verify Webhook Signature

**Python**
```python
import hmac
import hashlib

def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    """
    Verify webhook HMAC signature.

    Args:
        payload: Raw request body
        signature: Signature from X-Webhook-Signature header
        secret: Your webhook secret

    Returns:
        True if signature is valid
    """
    expected = hmac.new(
        secret.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(signature, expected)

# Flask example
from flask import Flask, request

app = Flask(__name__)
WEBHOOK_SECRET = "your_webhook_secret"

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    # Get signature
    signature = request.headers.get('X-Webhook-Signature')

    # Verify
    if not verify_webhook_signature(request.data, signature, WEBHOOK_SECRET):
        return {'error': 'Invalid signature'}, 401

    # Process webhook
    payload = request.json
    # ... handle event

    return {'status': 'success'}
```

**TypeScript**
```typescript
import crypto from 'crypto';
import express from 'express';

function verifyWebhookSignature(
  payload: Buffer,
  signature: string,
  secret: string
): boolean {
  const expected = crypto
    .createHmac('sha256', secret)
    .update(payload)
    .digest('hex');

  return crypto.timingSafeEqual(
    Buffer.from(signature),
    Buffer.from(expected)
  );
}

// Express example
const app = express();
const WEBHOOK_SECRET = 'your_webhook_secret';

app.use(express.json({
  verify: (req: any, res, buf) => {
    req.rawBody = buf;
  }
}));

app.post('/webhook', (req: any, res) => {
  const signature = req.headers['x-webhook-signature'];

  if (!verifyWebhookSignature(req.rawBody, signature, WEBHOOK_SECRET)) {
    return res.status(401).json({ error: 'Invalid signature' });
  }

  const payload = req.body;
  // ... handle event

  res.json({ status: 'success' });
});
```

---

## Testing

### Unit Tests

**Python (pytest)**
```python
# tests/test_documents.py
import pytest
from unittest.mock import Mock, patch
from ablage_sdk import AblageClient
from ablage_sdk.exceptions import AblageNotFoundError

@pytest.fixture
def client():
    """Create test client."""
    return AblageClient(api_key="test_key", base_url="https://test.api")

def test_get_document(client):
    """Test getting a document."""
    with patch.object(client.session, 'request') as mock_request:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'id': 'doc_123',
            'filename': 'test.pdf',
            'status': 'completed',
            'user_id': 'user_123',
            'size': 1024,
            'mime_type': 'application/pdf'
        }
        mock_request.return_value = mock_response

        doc = client.documents.get('doc_123')

        assert doc.id == 'doc_123'
        assert doc.filename == 'test.pdf'
        assert doc.status == 'completed'

def test_document_not_found(client):
    """Test document not found error."""
    with patch.object(client.session, 'request') as mock_request:
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = Exception()
        mock_request.return_value = mock_response

        with pytest.raises(AblageNotFoundError):
            client.documents.get('doc_invalid')
```

**TypeScript (Jest)**
```typescript
// tests/documents.test.ts
import { AblageClient } from '../src';
import { AblageNotFoundError } from '../src/exceptions';
import axios from 'axios';

jest.mock('axios');
const mockedAxios = axios as jest.Mocked<typeof axios>;

describe('DocumentsClient', () => {
  let client: AblageClient;

  beforeEach(() => {
    client = new AblageClient({
      apiKey: 'test_key',
      baseUrl: 'https://test.api'
    });
  });

  it('should get a document', async () => {
    const mockData = {
      id: 'doc_123',
      filename: 'test.pdf',
      status: 'completed',
      user_id: 'user_123',
      size: 1024,
      mime_type: 'application/pdf'
    };

    mockedAxios.create.mockReturnThis();
    mockedAxios.get.mockResolvedValue({ data: mockData });

    const doc = await client.documents.get('doc_123');

    expect(doc.id).toBe('doc_123');
    expect(doc.filename).toBe('test.pdf');
    expect(doc.status).toBe('completed');
  });

  it('should throw AblageNotFoundError for invalid document', async () => {
    mockedAxios.create.mockReturnThis();
    mockedAxios.get.mockRejectedValue({
      response: { status: 404, data: { message: 'Not found' } }
    });

    await expect(
      client.documents.get('doc_invalid')
    ).rejects.toThrow(AblageNotFoundError);
  });
});
```

---

## Best Practices

### 1. Use Environment Variables

```python
# Python
import os
from ablage_sdk import AblageClient

client = AblageClient(
    api_key=os.getenv("ABLAGE_API_KEY"),
    base_url=os.getenv("ABLAGE_BASE_URL")
)
```

```typescript
// TypeScript
const client = new AblageClient({
  apiKey: process.env.ABLAGE_API_KEY!,
  baseUrl: process.env.ABLAGE_BASE_URL
});
```

### 2. Handle Errors Gracefully

```python
# Python
try:
    doc = client.documents.get(doc_id)
except AblageNotFoundError:
    # Handle not found
    logger.warning(f"Document {doc_id} not found")
except AblageError as e:
    # Handle other errors
    logger.error(f"API error: {e}")
```

### 3. Use Timeouts

```python
# Python
client = AblageClient(
    api_key="...",
    timeout=30  # 30 seconds
)
```

```typescript
// TypeScript
const client = new AblageClient({
  apiKey: '...',
  timeout: 30000  // 30 seconds
});
```

### 4. Implement Retry Logic

```python
# Python - automatic retries
client = AblageClient(
    api_key="...",
    max_retries=3
)
```

### 5. Monitor Rate Limits

```python
# Python
from ablage_sdk.exceptions import AblageRateLimitError

try:
    doc = client.documents.upload(file, filename)
except AblageRateLimitError:
    # Implement backoff
    time.sleep(60)
```

---

## Troubleshooting

### Common Issues

**Issue 1: Authentication Failed**

```python
# Check API key
print(f"API Key: {os.getenv('ABLAGE_API_KEY')}")

# Verify it's being sent
import requests
response = requests.get(
    "https://api.ablage.example.com/api/v1/users/me",
    headers={"Authorization": f"Bearer {api_key}"}
)
print(response.status_code)
```

**Issue 2: Connection Timeout**

```python
# Increase timeout
client = AblageClient(
    api_key="...",
    timeout=60  # Increase to 60 seconds
)

# Check network connectivity
import socket
try:
    socket.create_connection(("api.ablage.example.com", 443), timeout=5)
    print("Connection successful")
except Exception as e:
    print(f"Connection failed: {e}")
```

**Issue 3: SSL Certificate Verification Failed**

```python
# Disable SSL verification (NOT recommended for production)
client = AblageClient(
    api_key="...",
    verify_ssl=False  # Only for testing!
)
```

**Issue 4: File Upload Fails**

```python
# Check file exists and is readable
import os
file_path = "invoice.pdf"

if not os.path.exists(file_path):
    print(f"File not found: {file_path}")
elif not os.access(file_path, os.R_OK):
    print(f"File not readable: {file_path}")
else:
    file_size = os.path.getsize(file_path)
    print(f"File size: {file_size} bytes")

    # Check file size limit (e.g., 50MB)
    MAX_FILE_SIZE = 50 * 1024 * 1024
    if file_size > MAX_FILE_SIZE:
        print(f"File too large: {file_size} > {MAX_FILE_SIZE}")
```

---

## Appendix

### A. Complete API Reference

**Documents**
- `upload(file, filename, ...)` - Upload document
- `get(document_id)` - Get document
- `list(page, page_size, ...)` - List documents
- `update(document_id, ...)` - Update document
- `delete(document_id)` - Delete document
- `download(document_id)` - Download file
- `wait_for_completion(document_id, ...)` - Wait for processing
- `get_extracted_text(document_id)` - Get extracted text
- `reprocess(document_id, ...)` - Reprocess with OCR

**Users**
- `get(user_id)` - Get user
- `list()` - List users
- `create(email, password, ...)` - Create user
- `update(user_id, ...)` - Update user
- `delete(user_id)` - Delete user

**Webhooks**
- `create(url, event_types, ...)` - Create webhook
- `get(webhook_id)` - Get webhook
- `list()` - List webhooks
- `update(webhook_id, ...)` - Update webhook
- `delete(webhook_id)` - Delete webhook
- `rotate_secret(webhook_id)` - Rotate secret

**Analytics**
- `get_usage()` - Get usage statistics
- `get_metrics(...)` - Get metrics

### B. SDK Comparison

| Feature | Python SDK | TypeScript SDK |
|---------|------------|----------------|
| Sync API | ✅ Yes | ❌ No |
| Async API | ✅ Yes (optional) | ✅ Yes (default) |
| Type Safety | ⚠️ Optional (type hints) | ✅ Full |
| Auto Retry | ✅ Yes | ✅ Yes |
| Rate Limiting | ✅ Yes | ✅ Yes |
| File Upload | ✅ Yes | ✅ Yes |
| Streaming | ✅ Yes | ✅ Yes |
| Webhooks | ✅ Verify only | ✅ Verify only |

### C. Version Compatibility

| SDK Version | API Version | Min Python | Min Node.js |
|-------------|-------------|------------|-------------|
| 1.0.x | v1 | 3.8+ | 14+ |
| 1.1.x | v1 | 3.8+ | 14+ |
| 2.0.x | v2 | 3.9+ | 16+ |

---

## Summary

Dieses API Client SDK Guide behandelt:

- **Python SDK**: Installation, Client, Resources, Models, Exceptions, Complete Examples
- **TypeScript/JavaScript SDK**: Installation, Client, Resources, Models, Exceptions, Complete Examples
- **Authentication**: API Keys, Environment Variables
- **Error Handling**: Exception Hierarchy, Error Handling Patterns
- **Rate Limiting**: Headers, Handling, Exponential Backoff
- **Retry Logic**: Automatic Retries, Custom Retry Logic
- **Pagination**: Manual Pagination, Iterator Helpers
- **File Uploads**: From File, Buffer/Bytes, Batch Upload
- **Webhooks Integration**: Signature Verification, Flask/Express Examples
- **Testing**: Unit Tests (pytest, Jest)
- **Best Practices**: Environment Variables, Error Handling, Timeouts
- **Troubleshooting**: Common Issues, Debug Scripts

Beide SDKs bieten:
- ✅ Type-safe API calls
- ✅ Automatic authentication
- ✅ Comprehensive error handling
- ✅ Retry logic with exponential backoff
- ✅ Rate limit handling
- ✅ File upload support
- ✅ Webhook signature verification
- ✅ Complete documentation
- ✅ Production-ready
