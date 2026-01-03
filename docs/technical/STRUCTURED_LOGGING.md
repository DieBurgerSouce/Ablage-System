# Structured Logging Implementation - Ablage-System

## Overview

The Ablage-System now features comprehensive **structured logging** using `structlog`, providing JSON-formatted logs with correlation IDs, performance metrics, and German language support.

## Features

### Core Features
- ✅ **JSON-formatted logs** for easy parsing and aggregation
- ✅ **Correlation IDs** for request tracing across services
- ✅ **German language** for all log messages
- ✅ **Performance metrics** (CPU, memory, GPU usage)
- ✅ **Sensitive data filtering** (GDPR compliance)
- ✅ **Request/response logging** with timing
- ✅ **Error categorization** and stack traces
- ✅ **Specialized loggers** for OCR, database, and security

### Technical Features
- Async and sync function support
- Retry logic with exponential backoff
- Context management for log enrichment
- Automatic exception logging
- Configurable log levels and outputs
- File and console output support

## Quick Start

### 1. Install Dependencies

```bash
pip install structlog==24.1.0 python-json-logger==2.0.7
```

### 2. Configure Logging in Main Application

```python
# app/main.py
from app.core.logging_config import configure_logging, get_logger
from app.middleware.logging_middleware import LoggingMiddleware

# Configure structured logging
configure_logging(
    log_level="INFO",
    log_format="json",  # or "console" for development
    log_file="logs/ablage_system.log",
    enable_performance=True,
    enable_sensitive_filter=True
)

# Get logger instance
logger = get_logger(__name__)

# Add logging middleware
app.add_middleware(LoggingMiddleware)

# Log application startup
logger.info("Ablage-System gestartet", version="1.0.0", umgebung="produktion")
```

### 3. Use Specialized Loggers

```python
from app.utils.logging_utils import ocr_logger, db_logger, security_logger

# OCR logging
ocr_logger.log_start(dokument_id="123", backend="deepseek")
ocr_logger.log_progress(dokument_id="123", fortschritt=50, nachricht="Text extrahiert")
ocr_logger.log_complete(dokument_id="123", backend="deepseek", dauer_ms=2500, zeichen_extrahiert=1500)

# Database logging
db_logger.log_query("SELECT * FROM documents", dauer_ms=15, zeilen=100)

# Security logging
security_logger.log_login_attempt(benutzer="max@example.com", erfolgreich=True, ip_adresse="192.168.1.1")
```

## Configuration

### Environment Variables

```bash
# Logging configuration
LOG_LEVEL=INFO                    # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_FORMAT=json                    # json or console
LOG_FILE=logs/ablage_system.log   # Optional file output
LOG_ENABLE_PERFORMANCE=true       # Include performance metrics
LOG_ENABLE_SENSITIVE_FILTER=true  # Filter sensitive data
LOG_SKIP_PATHS=/health,/metrics   # Paths to skip logging
```

### Programmatic Configuration

```python
from app.core.logging_config import configure_logging

configure_logging(
    log_level="DEBUG",
    log_format="console",  # Human-readable for development
    log_file=None,         # No file output
    enable_performance=False,  # Skip performance metrics in dev
    enable_sensitive_filter=True
)
```

## Log Structure

### JSON Log Format

```json
{
  "zeitstempel": "2025-11-26T10:30:45.123Z",
  "stufe": "INFORMATION",
  "level": "INFO",
  "nachricht": "OCR Verarbeitung abgeschlossen",
  "korrelations_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "dokument_id": "doc-123",
  "backend": "deepseek",
  "dauer_ms": 2500,
  "zeichen_extrahiert": 1500,
  "kategorie": "ocr",
  "ereignis": "ocr_abgeschlossen",
  "system": {
    "cpu_prozent": 45.2,
    "speicher_prozent": 62.8,
    "festplatte_prozent": 78.5
  },
  "gpu": {
    "verfuegbar": true,
    "speicher_verwendet": 4.2,
    "speicher_gesamt": 16.0
  },
  "anfrage": {
    "methode": "POST",
    "pfad": "/api/v1/ocr/process",
    "ip": "192.168.1.100",
    "user_agent": "Mozilla/5.0..."
  },
  "datei": "ocr_service.py",
  "funktion": "process_document",
  "zeile": 145
}
```

## Usage Examples

### 1. Basic Logging

```python
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# Simple log messages
logger.info("Dokument hochgeladen", dokument_id="123", groesse_mb=2.5)
logger.warning("Speicher niedrig", verfuegbar_gb=1.5)
logger.error("Verarbeitung fehlgeschlagen", fehler="GPU OOM")
```

### 2. Using Decorators

```python
from app.utils.logging_utils import log_execution_time, log_retry

@log_execution_time(operation_name="PDF Verarbeitung")
async def process_pdf(file_path: str) -> str:
    # Function automatically logs execution time
    return await extract_text(file_path)

@log_retry(max_retries=3, backoff_seconds=1.0)
async def connect_to_database() -> Connection:
    # Automatically retries with logging
    return await create_connection()
```

### 3. Context Management

```python
from app.utils.logging_utils import log_context

# Add context that will be included in all logs within the block
with log_context(benutzer_id="user-456", dokument_typ="rechnung"):
    logger.info("Verarbeitung gestartet")
    # These fields are automatically added to this log
    result = await process_document()
    logger.info("Verarbeitung abgeschlossen")
```

### 4. Request Tracking

```python
# Correlation IDs are automatically generated for each request
# All logs within a request share the same correlation ID

# In middleware:
correlation_id = str(uuid.uuid4())
correlation_id_var.set(correlation_id)

# In service:
logger.info("Service aufgerufen")  # Automatically includes correlation_id
```

## Specialized Loggers

### OCR Logger

```python
from app.utils.logging_utils import ocr_logger

# Full OCR workflow logging
ocr_logger.log_start(dokument_id="doc-789", backend="got_ocr")

for progress in [25, 50, 75, 100]:
    ocr_logger.log_progress(
        dokument_id="doc-789",
        fortschritt=progress,
        nachricht=f"{progress}% abgeschlossen"
    )

ocr_logger.log_complete(
    dokument_id="doc-789",
    backend="got_ocr",
    dauer_ms=3500,
    zeichen_extrahiert=2500
)

# On error
ocr_logger.log_error(
    dokument_id="doc-789",
    backend="got_ocr",
    fehler="GPU Speicher erschöpft"
)
```

### Database Logger

```python
from app.utils.logging_utils import db_logger

# Query logging
db_logger.log_query(
    query="INSERT INTO documents (id, name) VALUES (?, ?)",
    dauer_ms=25,
    zeilen=1
)

# Transaction logging
transaction_id = str(uuid.uuid4())
db_logger.log_transaction_start(transaction_id)

try:
    # Database operations
    await db.execute(query)
    db_logger.log_transaction_commit(transaction_id, dauer_ms=150)
except Exception as e:
    db_logger.log_transaction_rollback(transaction_id, grund=str(e))
```

### Security Logger

```python
from app.utils.logging_utils import security_logger

# Authentication logging
security_logger.log_login_attempt(
    benutzer="admin@example.com",
    erfolgreich=False,
    ip_adresse="192.168.1.100"
)

# Access control logging
security_logger.log_access_denied(
    benutzer="user@example.com",
    ressource="/admin/users",
    grund="Keine Administratorrechte"
)

# Rate limiting
security_logger.log_rate_limit_exceeded(
    ip_adresse="192.168.1.100",
    endpoint="/api/v1/ocr/process",
    limit=10
)

# Suspicious activity
security_logger.log_suspicious_activity(
    beschreibung="Mehrere fehlgeschlagene Anmeldeversuche",
    ip_adresse="192.168.1.100"
)
```

## Middleware Configuration

### Request/Response Logging

```python
from app.middleware.logging_middleware import LoggingMiddleware

app.add_middleware(
    LoggingMiddleware,
    skip_paths=['/health', '/metrics', '/favicon.ico'],
    log_request_body=False,  # Set to True for debugging
    log_response_body=False  # Set to True for debugging
)
```

### Error Logging

```python
from app.middleware.logging_middleware import ErrorLoggingMiddleware

app.add_middleware(ErrorLoggingMiddleware)
```

## Performance Monitoring

### Automatic Performance Metrics

When `enable_performance=True`, logs automatically include:

```json
{
  "system": {
    "cpu_prozent": 45.2,
    "speicher_prozent": 62.8,
    "festplatte_prozent": 78.5
  },
  "gpu": {
    "verfuegbar": true,
    "speicher_verwendet": 4.2,
    "speicher_gesamt": 16.0
  }
}
```

### Slow Request Detection

Requests taking longer than 5 seconds are automatically logged as warnings:

```json
{
  "nachricht": "Langsame Anfrage erkannt",
  "pfad": "/api/v1/ocr/process",
  "dauer_ms": 7500,
  "schwellenwert_ms": 5000
}
```

## GDPR Compliance

### Sensitive Data Filtering

The following fields are automatically redacted:

- password, passwort
- token, access_token, refresh_token
- api_key, secret
- email (can be configured)
- iban, credit_card, ssn

Example:

```json
{
  "benutzer": "max@example.com",
  "password": "***ZENSIERT***",
  "api_key": "***ZENSIERT***"
}
```

### Data Retention

Configure log rotation to comply with GDPR:

```python
from logging.handlers import TimedRotatingFileHandler

handler = TimedRotatingFileHandler(
    filename="logs/ablage_system.log",
    when="midnight",
    interval=1,
    backupCount=30  # Keep 30 days of logs
)
```

## Log Aggregation

### ELK Stack Integration

The JSON format is compatible with Elasticsearch:

```yaml
# filebeat.yml
filebeat.inputs:
  - type: log
    enabled: true
    paths:
      - /app/logs/*.log
    json.keys_under_root: true
    json.add_error_key: true

output.elasticsearch:
  hosts: ["localhost:9200"]
  index: "ablage-system-%{+yyyy.MM.dd}"
```

### Grafana Loki

```yaml
# promtail-config.yml
clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  - job_name: ablage_system
    static_configs:
      - targets:
          - localhost
        labels:
          job: ablage_system
          __path__: /app/logs/*.log
    pipeline_stages:
      - json:
          expressions:
            level: level
            korrelations_id: korrelations_id
            kategorie: kategorie
```

## Troubleshooting

### Common Issues

#### 1. Logs Not Appearing

```python
# Check log level
import logging
print(logging.getLogger().level)  # Should be 20 (INFO) or lower

# Ensure configuration is called
configure_logging(log_level="DEBUG")
```

#### 2. Performance Impact

```python
# Disable performance metrics in production if needed
configure_logging(enable_performance=False)

# Skip logging for high-frequency endpoints
app.add_middleware(
    LoggingMiddleware,
    skip_paths=['/health', '/metrics', '/static']
)
```

#### 3. Large Log Files

```python
# Use log rotation
from logging.handlers import RotatingFileHandler

handler = RotatingFileHandler(
    filename="logs/ablage_system.log",
    maxBytes=100_000_000,  # 100 MB
    backupCount=5
)
```

## Testing

### Unit Testing with Logs

```python
import pytest
from unittest.mock import Mock
import structlog

@pytest.fixture
def mock_logger():
    return Mock(spec=structlog.BoundLogger)

def test_ocr_processing(mock_logger):
    from app.utils.logging_utils import OCRLogger

    ocr_logger = OCRLogger(logger=mock_logger)
    ocr_logger.log_start("doc-123", "deepseek")

    mock_logger.info.assert_called_once_with(
        "OCR Verarbeitung gestartet",
        dokument_id="doc-123",
        backend="deepseek",
        ereignis="ocr_start"
    )
```

### Integration Testing

```python
def test_logging_middleware(client, caplog):
    response = client.post("/api/v1/ocr/process")

    # Check that correlation ID is in response
    assert "X-Correlation-ID" in response.headers

    # Check log output
    assert "Eingehende Anfrage" in caplog.text
    assert "Ausgehende Antwort" in caplog.text
```

## Best Practices

1. **Use structured data** instead of string formatting
   ```python
   # Good
   logger.info("Dokument verarbeitet", dokument_id="123", seiten=5)

   # Bad
   logger.info(f"Dokument 123 mit 5 Seiten verarbeitet")
   ```

2. **Include context** in logs
   ```python
   logger.info(
       "Operation abgeschlossen",
       benutzer_id=user.id,
       dokument_id=doc.id,
       dauer_ms=duration
   )
   ```

3. **Use appropriate log levels**
   - DEBUG: Detailed diagnostic information
   - INFO: General informational messages
   - WARNING: Warning messages for potentially harmful situations
   - ERROR: Error events that might still allow the application to continue
   - CRITICAL: Critical problems that might cause the application to abort

4. **Avoid logging sensitive data**
   - Never log passwords, tokens, or API keys
   - Be careful with personal data (GDPR)
   - Use the sensitive data filter

5. **Use correlation IDs** for distributed tracing
   - Automatically added by middleware
   - Pass to external services for end-to-end tracing

## Production Deployment

### Checklist

- [ ] Configure appropriate log level (INFO or WARNING)
- [ ] Set up log rotation or retention policies
- [ ] Configure log aggregation (ELK, Loki, etc.)
- [ ] Enable sensitive data filtering
- [ ] Set up monitoring alerts for ERROR and CRITICAL logs
- [ ] Configure backup of log files
- [ ] Test log shipping to centralized system
- [ ] Verify GDPR compliance for log retention

### Recommended Settings

```python
# Production configuration
configure_logging(
    log_level="INFO",
    log_format="json",
    log_file="/var/log/ablage_system/app.log",
    enable_performance=True,
    enable_sensitive_filter=True
)

# Add middleware with production settings
app.add_middleware(
    LoggingMiddleware,
    skip_paths=['/health', '/metrics', '/favicon.ico', '/static'],
    log_request_body=False,
    log_response_body=False
)
```

## Summary

The structured logging implementation provides:

- **Complete observability** with correlation IDs and performance metrics
- **German language support** throughout
- **GDPR compliance** with sensitive data filtering
- **Production-ready** with log rotation and aggregation support
- **Developer-friendly** with decorators and specialized loggers
- **Performance monitoring** with automatic metrics collection

All logging follows the "Feinpoliert und durchdacht" philosophy of the Ablage-System.