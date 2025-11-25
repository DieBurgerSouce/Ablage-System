# Generate API Documentation

You are generating comprehensive API documentation from the FastAPI application.

## Your Task

Create detailed API documentation beyond the auto-generated Swagger/OpenAPI docs:

### 1. Extract API Information

Analyze all FastAPI routers in `app/api/`:
- List all endpoints
- Extract route parameters, query parameters, request bodies
- Document response models
- Note authentication requirements
- Identify rate limits

### 2. Generate Comprehensive Docs

Create `docs/API.md` with:

#### Structure

```markdown
# Ablage-System API Documentation

**Base URL:** `http://localhost:8000` (development)
**Version:** v1
**Authentication:** Bearer Token (JWT)

## Authentication

### Obtain Token
`POST /api/v1/auth/login`

## Endpoints

### Documents

#### Upload Document
`POST /api/v1/documents/`

**Description:** Upload a document for OCR processing

**Authentication:** Required

**Request:**
- Content-Type: multipart/form-data
- Body:
  - `file` (file, required): Document file (PDF, PNG, JPG, TIFF)
  - `language` (string, optional): Document language (default: "de")

**Response:** 201 Created
```json
{
  "id": "uuid",
  "filename": "string",
  "status": "pending",
  "created_at": "datetime"
}
```

**Error Responses:**
- 400: Invalid file format
- 401: Authentication required
- 413: File too large (max 50MB)

**Example:**
```bash
curl -X POST \
  'http://localhost:8000/api/v1/documents/' \
  -H 'Authorization: Bearer TOKEN' \
  -F 'file=@document.pdf'
```

---

(Continue for all endpoints...)
```

### 3. Additional Sections

Include:

#### Rate Limits
Document rate limiting rules per endpoint

#### Error Codes
Comprehensive list of error codes and meanings (German messages)

#### Webhooks
If applicable, document webhook events

#### Pagination
Explain pagination parameters (skip, limit)

#### Filtering & Sorting
Document available filters and sort options

#### German Language
Note all user-facing text is in German

### 4. Code Examples

Provide examples in:
- cURL
- Python (requests library)
- JavaScript (fetch)

### 5. Postman Collection

Generate a Postman collection JSON file:
- `docs/postman/ablage-api.postman_collection.json`
- Include all endpoints
- Add example requests
- Configure environment variables

### 6. OpenAPI Enhancement

Update FastAPI app to enhance auto-generated docs:
- Add detailed descriptions
- Include examples in schemas
- Add tags for grouping
- Configure API metadata

## Output

Provide:
1. Complete API.md file
2. Postman collection JSON
3. Code to enhance OpenAPI in main.py
4. Summary of documented endpoints
