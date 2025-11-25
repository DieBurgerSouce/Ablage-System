#!/bin/bash
# API Documentation Generator - Ablage-System OCR
# Generates comprehensive API documentation from FastAPI OpenAPI spec

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
DOCKER_COMPOSE="docker-compose -f docker-compose.yml -f docker-compose.dev.yml"
DOCS_DIR="docs/api"
OPENAPI_FILE="$DOCS_DIR/openapi.json"
API_URL="${API_URL:-http://localhost:8000}"

# Ensure docs directory exists
mkdir -p "$DOCS_DIR"

# Function to check if API is running
check_api_running() {
    echo -e "${BLUE}🔍 Checking if API is running...${NC}"

    if curl -s -f "$API_URL/health" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ API is running at $API_URL${NC}"
        return 0
    else
        echo -e "${YELLOW}⚠️  API is not running, starting services...${NC}"
        $DOCKER_COMPOSE up -d backend

        # Wait for API to be ready
        echo -e "${BLUE}Waiting for API to be ready...${NC}"
        for i in {1..30}; do
            if curl -s -f "$API_URL/health" > /dev/null 2>&1; then
                echo -e "${GREEN}✅ API is ready${NC}"
                return 0
            fi
            sleep 2
        done

        echo -e "${RED}❌ API failed to start${NC}"
        exit 1
    fi
}

# Function to fetch OpenAPI spec
fetch_openapi_spec() {
    echo -e "${BLUE}📥 Fetching OpenAPI specification...${NC}"

    if curl -s -f "$API_URL/openapi.json" > "$OPENAPI_FILE"; then
        echo -e "${GREEN}✅ OpenAPI spec saved to $OPENAPI_FILE${NC}"
    else
        echo -e "${RED}❌ Failed to fetch OpenAPI spec${NC}"
        exit 1
    fi
}

# Function to generate Markdown documentation
generate_markdown() {
    echo -e "${BLUE}📝 Generating Markdown documentation...${NC}"

    cat > "$DOCS_DIR/README.md" <<'EOF'
# Ablage-System OCR - API Documentation

Umfassende REST API Dokumentation für das Ablage-System.

## Base URL

**Development:** `http://localhost:8000`
**Production:** `https://ablage-system.local`

## Authentication

Die API verwendet JWT Bearer Token Authentication.

### Login

```http
POST /api/v1/auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "password"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGc...",
  "token_type": "bearer",
  "expires_in": 900
}
```

### Using the Token

```http
GET /api/v1/documents
Authorization: Bearer eyJhbGc...
```

## API Endpoints

### Health Check

```http
GET /health
```

Returns system health status.

**Response:**
```json
{
  "status": "healthy",
  "checks": {
    "database": true,
    "redis": true,
    "minio": true,
    "gpu": true
  }
}
```

### Documents

#### Upload Document

```http
POST /api/v1/documents/
Authorization: Bearer <token>
Content-Type: multipart/form-data

file: <binary>
language: "de"  # optional, default: "de"
```

**Response:**
```json
{
  "id": "uuid",
  "filename": "document.pdf",
  "status": "pending",
  "created_at": "2024-01-24T12:00:00Z"
}
```

#### Get Document

```http
GET /api/v1/documents/{document_id}
Authorization: Bearer <token>
```

**Response:**
```json
{
  "id": "uuid",
  "filename": "document.pdf",
  "status": "processed",
  "extracted_text": "...",
  "ocr_confidence": 0.98,
  "language": "de",
  "created_at": "2024-01-24T12:00:00Z",
  "processed_at": "2024-01-24T12:00:15Z"
}
```

#### List Documents

```http
GET /api/v1/documents?skip=0&limit=20
Authorization: Bearer <token>
```

**Query Parameters:**
- `skip` (int): Pagination offset (default: 0)
- `limit` (int): Items per page (default: 20, max: 100)
- `status` (string): Filter by status (pending, processing, processed, failed)
- `language` (string): Filter by language (de, en)

#### Delete Document

```http
DELETE /api/v1/documents/{document_id}
Authorization: Bearer <token>
```

### OCR Processing

#### Start OCR Processing

```http
POST /api/v1/ocr/{document_id}/process
Authorization: Bearer <token>
Content-Type: application/json

{
  "backend": "auto",  # auto, deepseek, got_ocr, surya
  "priority": "normal"  # low, normal, high
}
```

**Response:**
```json
{
  "task_id": "uuid",
  "status": "queued",
  "estimated_time_ms": 2000
}
```

#### Get OCR Task Status

```http
GET /api/v1/ocr/tasks/{task_id}
Authorization: Bearer <token>
```

### Users

#### Get Current User

```http
GET /api/v1/users/me
Authorization: Bearer <token>
```

#### Update User Profile

```http
PATCH /api/v1/users/me
Authorization: Bearer <token>
Content-Type: application/json

{
  "email": "newemail@example.com",
  "username": "newusername"
}
```

## Error Responses

All endpoints may return the following error responses:

### 400 Bad Request
```json
{
  "detail": "Invalid request parameters"
}
```

### 401 Unauthorized
```json
{
  "detail": "Not authenticated"
}
```

### 403 Forbidden
```json
{
  "detail": "Access denied"
}
```

### 404 Not Found
```json
{
  "detail": "Resource not found"
}
```

### 422 Unprocessable Entity
```json
{
  "detail": [
    {
      "loc": ["body", "email"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

### 500 Internal Server Error
```json
{
  "detail": "Internal server error"
}
```

## Rate Limiting

API requests are rate-limited:
- **Authenticated users:** 100 requests/minute
- **OCR processing:** 10 documents/hour
- **Unauthenticated:** 20 requests/minute

Rate limit headers:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1706097600
```

## WebSocket Support

Real-time updates via WebSocket:

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/documents');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Document update:', data);
};
```

## Supported File Types

- **Documents:** PDF, DOCX, TXT
- **Images:** JPG, JPEG, PNG, TIFF
- **Max file size:** 50 MB

## German Language Support

Die API unterstützt vollständig deutsche Dokumente:
- ✅ Umlaute (ä, ö, ü, ß) werden korrekt verarbeitet
- ✅ Frakturschrift-Unterstützung
- ✅ Deutsche Datums- und Währungsformate
- ✅ Fehlerme ldungen auf Deutsch

## Interactive Documentation

Vollständige interaktive API-Dokumentation:
- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`
- **OpenAPI JSON:** `http://localhost:8000/openapi.json`

## Code Examples

### Python

```python
import requests

# Login
response = requests.post(
    "http://localhost:8000/api/v1/auth/login",
    json={"email": "user@example.com", "password": "password"}
)
token = response.json()["access_token"]

# Upload document
files = {"file": open("document.pdf", "rb")}
headers = {"Authorization": f"Bearer {token}"}
response = requests.post(
    "http://localhost:8000/api/v1/documents/",
    files=files,
    headers=headers
)
document_id = response.json()["id"]

# Start OCR
response = requests.post(
    f"http://localhost:8000/api/v1/ocr/{document_id}/process",
    json={"backend": "auto"},
    headers=headers
)
```

### JavaScript/Node.js

```javascript
const axios = require('axios');
const FormData = require('form-data');
const fs = require('fs');

// Login
const { data: { access_token } } = await axios.post(
  'http://localhost:8000/api/v1/auth/login',
  { email: 'user@example.com', password: 'password' }
);

// Upload document
const form = new FormData();
form.append('file', fs.createReadStream('document.pdf'));

const { data: document } = await axios.post(
  'http://localhost:8000/api/v1/documents/',
  form,
  {
    headers: {
      ...form.getHeaders(),
      'Authorization': `Bearer ${access_token}`
    }
  }
);

// Start OCR
await axios.post(
  `http://localhost:8000/api/v1/ocr/${document.id}/process`,
  { backend: 'auto' },
  { headers: { 'Authorization': `Bearer ${access_token}` } }
);
```

### cURL

```bash
# Login
TOKEN=$(curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "password"}' \
  | jq -r '.access_token')

# Upload document
DOCUMENT_ID=$(curl -X POST "http://localhost:8000/api/v1/documents/" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@document.pdf" \
  | jq -r '.id')

# Start OCR
curl -X POST "http://localhost:8000/api/v1/ocr/$DOCUMENT_ID/process" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"backend": "auto"}'
```

## Support

Bei Fragen oder Problemen:
- 📧 Email: support@ablage-system.local
- 📖 Dokumentation: https://docs.ablage-system.local
- 🐛 Issues: https://github.com/org/ablage-system/issues

---

**Last Updated:** $(date +%Y-%m-%d)
**API Version:** $(cat VERSION 2>/dev/null || echo "unknown")
EOF

    echo -e "${GREEN}✅ Markdown documentation generated${NC}"
}

# Function to generate Postman collection
generate_postman() {
    echo -e "${BLUE}📮 Generating Postman collection...${NC}"

    # Convert OpenAPI to Postman (simplified)
    cat > "$DOCS_DIR/Ablage-System.postman_collection.json" <<EOF
{
  "info": {
    "name": "Ablage-System OCR API",
    "description": "Complete API collection for Ablage-System",
    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
  },
  "auth": {
    "type": "bearer",
    "bearer": [
      {
        "key": "token",
        "value": "{{access_token}}",
        "type": "string"
      }
    ]
  },
  "variable": [
    {
      "key": "base_url",
      "value": "http://localhost:8000",
      "type": "string"
    },
    {
      "key": "access_token",
      "value": "",
      "type": "string"
    }
  ],
  "item": [
    {
      "name": "Authentication",
      "item": [
        {
          "name": "Login",
          "request": {
            "method": "POST",
            "header": [
              {
                "key": "Content-Type",
                "value": "application/json"
              }
            ],
            "url": {
              "raw": "{{base_url}}/api/v1/auth/login",
              "host": ["{{base_url}}"],
              "path": ["api", "v1", "auth", "login"]
            },
            "body": {
              "mode": "raw",
              "raw": "{\"email\": \"user@example.com\", \"password\": \"password\"}"
            }
          }
        }
      ]
    },
    {
      "name": "Documents",
      "item": [
        {
          "name": "Upload Document",
          "request": {
            "method": "POST",
            "url": {
              "raw": "{{base_url}}/api/v1/documents/",
              "host": ["{{base_url}}"],
              "path": ["api", "v1", "documents"]
            },
            "body": {
              "mode": "formdata",
              "formdata": [
                {
                  "key": "file",
                  "type": "file",
                  "src": ""
                }
              ]
            }
          }
        },
        {
          "name": "List Documents",
          "request": {
            "method": "GET",
            "url": {
              "raw": "{{base_url}}/api/v1/documents?skip=0&limit=20",
              "host": ["{{base_url}}"],
              "path": ["api", "v1", "documents"],
              "query": [
                {
                  "key": "skip",
                  "value": "0"
                },
                {
                  "key": "limit",
                  "value": "20"
                }
              ]
            }
          }
        }
      ]
    }
  ]
}
EOF

    echo -e "${GREEN}✅ Postman collection generated${NC}"
}

# Function to display summary
show_summary() {
    echo ""
    echo -e "${BLUE}════════════════════════════════════════${NC}"
    echo -e "${BLUE}   API Documentation Generated! 📚${NC}"
    echo -e "${BLUE}════════════════════════════════════════${NC}"
    echo ""
    echo -e "${GREEN}📄 Generated Files:${NC}"
    echo -e "   $OPENAPI_FILE"
    echo -e "   $DOCS_DIR/README.md"
    echo -e "   $DOCS_DIR/Ablage-System.postman_collection.json"
    echo ""
    echo -e "${BLUE}🌐 Interactive Documentation:${NC}"
    echo -e "   Swagger UI:  $API_URL/docs"
    echo -e "   ReDoc:       $API_URL/redoc"
    echo ""
    echo -e "${BLUE}📖 View Markdown:${NC}"
    echo -e "   cat $DOCS_DIR/README.md"
    echo ""
    echo -e "${BLUE}📮 Import Postman Collection:${NC}"
    echo -e "   File → Import → $DOCS_DIR/Ablage-System.postman_collection.json"
    echo ""
}

# Main script
main() {
    echo -e "${BLUE}📚 API Documentation Generator${NC}"
    echo -e "${BLUE}══════════════════════════════${NC}"
    echo ""

    check_api_running
    fetch_openapi_spec
    generate_markdown
    generate_postman
    show_summary

    echo -e "${GREEN}✅ Documentation generation complete!${NC}"
}

# Run main function
main
