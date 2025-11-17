📝 ERROR HANDLING & LOGGING GUIDE - TEIL 1
Comprehensive Guide to Logging, Error Tracking & Debugging

📋 TABLE OF CONTENTS

Introduction
Structured Logging
Log Levels & Formatting
Centralized Logging (ELK Stack)
Error Tracking with Sentry


🎯 INTRODUCTION
Why Proper Logging Matters
┌─────────────────────────────────────────────────────────┐
│                   LOGGING BENEFITS                      │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  🔍 Debugging        → Find and fix issues quickly      │
│  📊 Monitoring       → Track system health              │
│  🔐 Security         → Detect suspicious activities     │
│  📈 Analytics        → Understand user behavior         │
│  🔔 Alerting         → Get notified of problems         │
│  📝 Audit Trail      → Compliance and accountability    │
│  🎯 Performance      → Identify bottlenecks             │
│                                                         │
└─────────────────────────────────────────────────────────┘
Logging Architecture Overview
┌──────────────┐         ┌──────────────┐         ┌──────────────┐
│  FastAPI     │────────▶│   Loguru/    │────────▶│  Log Files   │
│ Application  │  Logs   │  Structlog   │  Write  │  (JSON)      │
└──────────────┘         └──────────────┘         └──────────────┘
       │                        │                         │
       │                        │                         │
       ▼                        ▼                         ▼
┌──────────────┐         ┌──────────────┐         ┌──────────────┐
│    Sentry    │         │  Filebeat/   │         │ Elasticsearch│
│ (Errors)     │         │  Fluentd     │         │   (Search)   │
└──────────────┘         └──────────────┘         └──────────────┘
                                │
                                ▼
                         ┌──────────────┐
                         │   Kibana     │
                         │ (Visualize)  │
                         └──────────────┘

🏗️ STRUCTURED LOGGING
1. Loguru Setup (Simple & Powerful)
python# backend/core/logging/loguru_config.py

from loguru import logger
import sys
from pathlib import Path
from typing import Dict, Any
import json

from core.config import settings


class LoguruConfig:
    """
    Loguru logging configuration.
    
    Features:
    - Structured logging (JSON)
    - Automatic rotation
    - Colored console output
    - Context injection
    - Performance
    """
    
    @staticmethod
    def setup():
        """Configure Loguru logger"""
        
        # Remove default handler
        logger.remove()
        
        # ============================================
        # CONSOLE HANDLER (Development)
        # ============================================
        
        if settings.ENVIRONMENT == "development":
            logger.add(
                sys.stderr,
                format=(
                    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
                    "<level>{level: <8}</level> | "
                    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
                    "<level>{message}</level>"
                ),
                level="DEBUG",
                colorize=True,
                backtrace=True,
                diagnose=True
            )
        
        # ============================================
        # FILE HANDLER (JSON Structured)
        # ============================================
        
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        # Application logs
        logger.add(
            log_dir / "app_{time:YYYY-MM-DD}.log",
            format="{message}",
            level="INFO",
            rotation="00:00",  # Rotate at midnight
            retention="30 days",  # Keep logs for 30 days
            compression="zip",  # Compress old logs
            serialize=True,  # JSON format
            backtrace=True,
            diagnose=True,
            enqueue=True  # Async logging
        )
        
        # Error logs (separate file)
        logger.add(
            log_dir / "error_{time:YYYY-MM-DD}.log",
            format="{message}",
            level="ERROR",
            rotation="00:00",
            retention="90 days",  # Keep errors longer
            compression="zip",
            serialize=True,
            backtrace=True,
            diagnose=True,
            enqueue=True
        )
        
        # ============================================
        # PERFORMANCE LOGS (Optional)
        # ============================================
        
        logger.add(
            log_dir / "performance_{time:YYYY-MM-DD}.log",
            format="{message}",
            level="INFO",
            rotation="100 MB",  # Rotate on size
            retention="7 days",
            compression="zip",
            serialize=True,
            filter=lambda record: "performance" in record["extra"]
        )
        
        logger.info("Logging configured successfully")


# ============================================
# CONTEXT MANAGERS FOR LOGGING
# ============================================

from contextlib import contextmanager
import time


@contextmanager
def log_execution_time(operation: str):
    """
    Context manager to log execution time.
    
    Usage:
        with log_execution_time("database_query"):
            result = db.query(...)
    """
    start_time = time.time()
    try:
        yield
    finally:
        elapsed = time.time() - start_time
        logger.info(
            f"{operation} completed",
            performance=True,
            elapsed_time=elapsed
        )


@contextmanager
def log_context(**kwargs):
    """
    Context manager to add context to logs.
    
    Usage:
        with log_context(user_id=123, request_id="abc"):
            logger.info("Processing request")
    """
    token = logger.contextualize(**kwargs)
    try:
        yield
    finally:
        token.reset()
2. Structlog Setup (Advanced)
python# backend/core/logging/structlog_config.py

import structlog
from typing import Any, Dict
import logging


class StructlogConfig:
    """
    Structlog configuration for advanced structured logging.
    
    Features:
    - Consistent key-value logging
    - Automatic context binding
    - Better integration with external systems
    """
    
    @staticmethod
    def setup():
        """Configure structlog"""
        
        structlog.configure(
            processors=[
                # Add log level
                structlog.stdlib.add_log_level,
                
                # Add logger name
                structlog.stdlib.add_logger_name,
                
                # Add timestamp
                structlog.processors.TimeStamper(fmt="iso"),
                
                # Add stack info for exceptions
                structlog.processors.StackInfoRenderer(),
                
                # Format exceptions
                structlog.processors.format_exc_info,
                
                # Decode unicode
                structlog.processors.UnicodeDecoder(),
                
                # Final processor: JSON renderer
                structlog.processors.JSONRenderer()
            ],
            
            # Wrapper class
            wrapper_class=structlog.stdlib.BoundLogger,
            
            # Context class
            context_class=dict,
            
            # Logger factory
            logger_factory=structlog.stdlib.LoggerFactory(),
            
            # Cache logger
            cache_logger_on_first_use=True,
        )


# ============================================
# USAGE EXAMPLES
# ============================================

# Get logger
log = structlog.get_logger()

# Simple logging
log.info("user_logged_in", user_id=123, ip="192.168.1.1")

# Bind context
log = log.bind(request_id="abc-123")
log.info("processing_request")  # request_id automatically included

# Unbind context
log = log.unbind("request_id")

📊 LOG LEVELS & FORMATTING
1. Standard Log Levels
python# backend/core/logging/levels.py

from enum import Enum


class LogLevel(str, Enum):
    """Standard logging levels"""
    
    DEBUG = "DEBUG"          # Detailed information for debugging
    INFO = "INFO"            # General informational messages
    WARNING = "WARNING"      # Warning messages
    ERROR = "ERROR"          # Error messages
    CRITICAL = "CRITICAL"    # Critical errors


# ============================================
# WHEN TO USE EACH LEVEL
# ============================================

"""
DEBUG:
- Variable values during execution
- Function entry/exit points
- Detailed state information
- Only in development

INFO:
- Request received/completed
- User actions
- Business events
- State changes

WARNING:
- Deprecated features
- Non-critical failures
- Retry attempts
- Configuration issues

ERROR:
- Exceptions
- Failed operations
- Integration failures
- Data validation errors

CRITICAL:
- System failures
- Data corruption
- Security breaches
- Service unavailable
"""
2. Custom Log Formatters
python# backend/core/logging/formatters.py

import json
from datetime import datetime
from typing import Dict, Any


class JSONFormatter:
    """
    Custom JSON formatter for structured logs.
    
    Output format:
    {
        "timestamp": "2024-01-15T10:30:00.123Z",
        "level": "INFO",
        "logger": "app.api",
        "message": "Request processed",
        "context": {...}
    }
    """
    
    @staticmethod
    def format_log(record: Dict[str, Any]) -> str:
        """Format log record as JSON"""
        
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.get("level", {}).get("name", "INFO"),
            "logger": record.get("name", ""),
            "message": record.get("message", ""),
            "function": record.get("function", ""),
            "line": record.get("line", 0),
        }
        
        # Add extra fields
        if "extra" in record:
            log_entry["context"] = record["extra"]
        
        # Add exception info
        if "exception" in record and record["exception"]:
            log_entry["exception"] = {
                "type": record["exception"].type.__name__,
                "value": str(record["exception"].value),
                "traceback": record["exception"].traceback
            }
        
        return json.dumps(log_entry)


class ColoredConsoleFormatter:
    """
    Colored console formatter for development.
    
    Example output:
    [2024-01-15 10:30:00] INFO     app.api:process_request:42 - Request processed
    """
    
    COLORS = {
        "DEBUG": "\033[36m",      # Cyan
        "INFO": "\033[32m",       # Green
        "WARNING": "\033[33m",    # Yellow
        "ERROR": "\033[31m",      # Red
        "CRITICAL": "\033[35m",   # Magenta
        "RESET": "\033[0m"
    }
    
    @staticmethod
    def format_log(record: Dict[str, Any]) -> str:
        """Format log with colors"""
        
        level = record.get("level", {}).get("name", "INFO")
        color = ColoredConsoleFormatter.COLORS.get(level, "")
        reset = ColoredConsoleFormatter.COLORS["RESET"]
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger_name = record.get("name", "")
        function = record.get("function", "")
        line = record.get("line", 0)
        message = record.get("message", "")
        
        formatted = (
            f"{color}[{timestamp}] {level:8s}{reset} "
            f"{logger_name}:{function}:{line} - {message}"
        )
        
        return formatted
```

---

## 🔍 CENTRALIZED LOGGING (ELK STACK)

### 1. ELK Stack Overview
```
┌──────────────────────────────────────────────────────────┐
│                    ELK STACK COMPONENTS                  │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  Elasticsearch  → Store & Search logs                    │
│  Logstash       → Process & Transform logs               │
│  Kibana         → Visualize & Analyze logs               │
│  Filebeat       → Ship logs from servers                 │
│                                                          │
└──────────────────────────────────────────────────────────┘
2. Docker Compose Setup
yaml# docker-compose.elk.yml

version: '3.8'

services:
  # ============================================
  # ELASTICSEARCH
  # ============================================
  
  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.11.0
    container_name: elasticsearch
    environment:
      - discovery.type=single-node
      - "ES_JAVA_OPTS=-Xms512m -Xmx512m"
      - xpack.security.enabled=false
    ports:
      - "9200:9200"
      - "9300:9300"
    volumes:
      - elasticsearch_data:/usr/share/elasticsearch/data
    networks:
      - elk
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:9200 || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 5
  
  # ============================================
  # KIBANA
  # ============================================
  
  kibana:
    image: docker.elastic.co/kibana/kibana:8.11.0
    container_name: kibana
    ports:
      - "5601:5601"
    environment:
      - ELASTICSEARCH_HOSTS=http://elasticsearch:9200
    networks:
      - elk
    depends_on:
      - elasticsearch
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:5601 || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 5
  
  # ============================================
  # LOGSTASH
  # ============================================
  
  logstash:
    image: docker.elastic.co/logstash/logstash:8.11.0
    container_name: logstash
    ports:
      - "5044:5044"
      - "9600:9600"
    volumes:
      - ./logstash/config:/usr/share/logstash/config
      - ./logstash/pipeline:/usr/share/logstash/pipeline
    environment:
      - "LS_JAVA_OPTS=-Xmx256m -Xms256m"
    networks:
      - elk
    depends_on:
      - elasticsearch
  
  # ============================================
  # FILEBEAT
  # ============================================
  
  filebeat:
    image: docker.elastic.co/beats/filebeat:8.11.0
    container_name: filebeat
    user: root
    volumes:
      - ./filebeat/filebeat.yml:/usr/share/filebeat/filebeat.yml:ro
      - /var/lib/docker/containers:/var/lib/docker/containers:ro
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ./logs:/logs:ro
    command: filebeat -e -strict.perms=false
    networks:
      - elk
    depends_on:
      - elasticsearch
      - logstash

volumes:
  elasticsearch_data:
    driver: local

networks:
  elk:
    driver: bridge
3. Filebeat Configuration
yaml# filebeat/filebeat.yml

filebeat.inputs:
  # ============================================
  # APPLICATION LOGS
  # ============================================
  
  - type: log
    enabled: true
    paths:
      - /logs/app_*.log
    json.keys_under_root: true
    json.add_error_key: true
    fields:
      log_type: application
      environment: ${ENVIRONMENT:production}
    fields_under_root: true
  
  # ============================================
  # ERROR LOGS
  # ============================================
  
  - type: log
    enabled: true
    paths:
      - /logs/error_*.log
    json.keys_under_root: true
    json.add_error_key: true
    fields:
      log_type: error
      environment: ${ENVIRONMENT:production}
      severity: high
    fields_under_root: true
  
  # ============================================
  # PERFORMANCE LOGS
  # ============================================
  
  - type: log
    enabled: true
    paths:
      - /logs/performance_*.log
    json.keys_under_root: true
    json.add_error_key: true
    fields:
      log_type: performance
      environment: ${ENVIRONMENT:production}
    fields_under_root: true

# ============================================
# OUTPUT TO ELASTICSEARCH
# ============================================

output.elasticsearch:
  hosts: ["elasticsearch:9200"]
  index: "app-logs-%{+yyyy.MM.dd}"
  
# OR OUTPUT TO LOGSTASH
# output.logstash:
#   hosts: ["logstash:5044"]

# ============================================
# PROCESSORS
# ============================================

processors:
  - add_host_metadata:
      when.not.contains.tags: forwarded
  - add_docker_metadata: ~
  - add_fields:
      target: ''
      fields:
        service: ${SERVICE_NAME:myapp}

# ============================================
# LOGGING
# ============================================

logging.level: info
logging.to_files: true
logging.files:
  path: /var/log/filebeat
  name: filebeat
  keepfiles: 7
  permissions: 0644
4. Logstash Pipeline
ruby# logstash/pipeline/app-logs.conf

input {
  beats {
    port => 5044
  }
}

filter {
  # ============================================
  # PARSE JSON
  # ============================================
  
  if [message] =~ /^\{.*\}$/ {
    json {
      source => "message"
    }
  }
  
  # ============================================
  # ADD GEO LOCATION (if IP present)
  # ============================================
  
  if [ip] {
    geoip {
      source => "ip"
      target => "geoip"
    }
  }
  
  # ============================================
  # ENRICH WITH METADATA
  # ============================================
  
  mutate {
    add_field => {
      "[@metadata][index_prefix]" => "app-logs"
    }
  }
  
  # ============================================
  # PARSE TIMESTAMPS
  # ============================================
  
  date {
    match => [ "timestamp", "ISO8601" ]
    target => "@timestamp"
  }
}

output {
  elasticsearch {
    hosts => ["elasticsearch:9200"]
    index => "%{[@metadata][index_prefix]}-%{+YYYY.MM.dd}"
  }
  
  # Debug output (optional)
  # stdout { codec => rubydebug }
}

🚨 ERROR TRACKING WITH SENTRY
1. Sentry Setup (Self-Hosted)
bash# Install Sentry (Self-Hosted)
git clone https://github.com/getsentry/self-hosted.git
cd self-hosted
./install.sh

# Start Sentry
docker-compose up -d
2. Python Integration
python# requirements.txt
sentry-sdk[fastapi]==1.40.0
python# backend/core/sentry/config.py

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.redis import RedisIntegration
from sentry_sdk.integrations.celery import CeleryIntegration
import logging


def init_sentry(
    dsn: str,
    environment: str = "production",
    sample_rate: float = 1.0,
    traces_sample_rate: float = 0.1
):
    """
    Initialize Sentry for error tracking and performance monitoring.
    
    Args:
        dsn: Your Sentry DSN (from self-hosted instance)
        environment: Environment name (production, staging, development)
        sample_rate: Error sampling rate (1.0 = 100%)
        traces_sample_rate: Performance monitoring rate (0.1 = 10%)
    """
    
    # Logging integration
    sentry_logging = LoggingIntegration(
        level=logging.INFO,        # Capture info and above as breadcrumbs
        event_level=logging.ERROR  # Send errors as events
    )
    
    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        
        # Integrations
        integrations=[
            FastApiIntegration(),
            sentry_logging,
            RedisIntegration(),
            CeleryIntegration(),
        ],
        
        # Performance Monitoring
        traces_sample_rate=traces_sample_rate,
        profiles_sample_rate=0.1,  # Profile 10% of transactions
        
        # Error Sampling
        sample_rate=sample_rate,
        
        # Release tracking
        release=get_version(),
        
        # Additional context
        attach_stacktrace=True,
        send_default_pii=False,  # Privacy: Don't send personal data
        
        # Before send hook (filter sensitive data)
        before_send=before_send_handler,
    )


def get_version() -> str:
    """Get current service version"""
    try:
        with open("VERSION", "r") as f:
            return f.read().strip()
    except:
        return "unknown"


def before_send_handler(event, hint):
    """
    Filter sensitive data before sending to Sentry.
    
    This runs before every event is sent to Sentry.
    Use it to remove PII, secrets, etc.
    """
    
    # Remove sensitive headers
    if "request" in event and "headers" in event["request"]:
        headers = event["request"]["headers"]
        sensitive_headers = ["Authorization", "Cookie", "X-Api-Key"]
        for header in sensitive_headers:
            if header in headers:
                headers[header] = "[Filtered]"
    
    # Remove sensitive cookies
    if "request" in event and "cookies" in event["request"]:
        event["request"]["cookies"] = "[Filtered]"
    
    # Remove password fields
    if "request" in event and "data" in event["request"]:
        data = event["request"]["data"]
        if isinstance(data, dict):
            for key in ["password", "token", "secret"]:
                if key in data:
                    data[key] = "[Filtered]"
    
    return event
3. FastAPI Integration
python# backend/main.py

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette import status
import traceback
from loguru import logger
from sentry_sdk import capture_exception, set_user, set_context

from core.sentry.config import init_sentry


app = FastAPI(title="My API")


# ============================================
# STARTUP: INITIALIZE SENTRY
# ============================================

@app.on_event("startup")
async def startup_event():
    init_sentry(
        dsn=os.getenv("SENTRY_DSN"),
        environment=os.getenv("ENVIRONMENT", "production"),
        sample_rate=1.0,
        traces_sample_rate=0.1
    )


# ============================================
# SENTRY CONTEXT HELPERS
# ============================================

def set_user_context(user_id: str, email: str = None, username: str = None):
    """Set user context in Sentry"""
    set_user({
        "id": user_id,
        "email": email,
        "username": username
    })


def set_request_context(request: Request):
    """Set request context in Sentry"""
    set_context("request", {
        "url": str(request.url),
        "method": request.method,
        "headers": dict(request.headers),
        "query_params": dict(request.query_params),
    })


def add_breadcrumb(message: str, category: str = "default", **data):
    """Add breadcrumb to Sentry"""
    from sentry_sdk import add_breadcrumb as sentry_add_breadcrumb
    sentry_add_breadcrumb(
        message=message,
        category=category,
        data=data,
        level="info"
    )


# ============================================
# VALIDATION ERROR HANDLER
# ============================================

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError
):
    """Handle validation errors"""
    
    # Log validation error
    logger.warning(
        "Validation error",
        extra={
            "path": request.url.path,
            "errors": exc.errors(),
            "body": exc.body
        }
    )
    
    # Don't send to Sentry (user errors, not system errors)
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": exc.errors(),
            "body": exc.body
        }
    )


# ============================================
# HTTP EXCEPTION HANDLER
# ============================================

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException
):
    """Handle HTTP exceptions"""
    
    # Log HTTP error
    logger.error(
        f"HTTP {exc.status_code} error",
        extra={
            "path": request.url.path,
            "status_code": exc.status_code,
            "detail": exc.detail
        }
    )
    
    # Only send 5xx errors to Sentry
    if exc.status_code >= 500:
        capture_exception(exc)
    
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )


# ============================================
# GENERAL EXCEPTION HANDLER
# ============================================

@app.exception_handler(Exception)
async def general_exception_handler(
    request: Request,
    exc: Exception
):
    """Handle all other exceptions"""
    
    # Log error with full traceback
    logger.exception(
        "Unhandled exception",
        extra={
            "path": request.url.path,
            "method": request.method,
            "error": str(exc),
            "traceback": traceback.format_exc()
        }
    )
    
    # Capture in Sentry
    capture_exception(exc)
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Internal server error",
            "type": type(exc).__name__
        }
    )


# ============================================
# MIDDLEWARE FOR CONTEXT
# ============================================

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
import uuid


class SentryContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add context to Sentry events.
    
    Adds:
    - Request ID
    - User information
    - Request details
    """
    
    async def dispatch(self, request: Request, call_next):
        """Process request and add context"""
        
        # Generate request ID
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        
        # Set transaction name
        with sentry_sdk.configure_scope() as scope:
            scope.set_transaction_name(
                f"{request.method} {request.url.path}"
            )
            
            # Add request context
            scope.set_context("request", {
                "request_id": request_id,
                "method": request.method,
                "url": str(request.url),
                "headers": dict(request.headers),
                "query_params": dict(request.query_params),
            })
            
            # Add user context if authenticated
            if hasattr(request.state, "user"):
                user = request.state.user
                set_user_context(
                    user_id=str(user.id),
                    email=user.email,
                    username=user.username
                )
        
        # Add breadcrumb
        add_breadcrumb(
            message=f"{request.method} {request.url.path}",
            category="http",
            data={
                "request_id": request_id,
                "method": request.method,
                "url": str(request.url)
            }
        )
        
        # Process request
        response = await call_next(request)
        
        return response


# Add middleware
app.add_middleware(SentryContextMiddleware)





📝 ERROR HANDLING & LOGGING GUIDE - TEIL 2
Exception Handling, Request Tracking & Debugging

📋 TABLE OF CONTENTS (TEIL 2)

Exception Handling Best Practices
Request ID Tracking
Log Rotation & Management
Debugging Strategies
Production Best Practices


⚠️ EXCEPTION HANDLING BEST PRACTICES
1. Custom Exception Hierarchy
python# backend/core/exceptions.py

from typing import Optional, Any, Dict
from fastapi import status


class BaseAPIException(Exception):
    """
    Base exception for all API exceptions.
    
    All custom exceptions should inherit from this.
    """
    
    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


# ============================================
# CLIENT ERRORS (4xx)
# ============================================

class ValidationException(BaseAPIException):
    """Validation error (400)"""
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details
        )


class AuthenticationException(BaseAPIException):
    """Authentication error (401)"""
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED
        )


class AuthorizationException(BaseAPIException):
    """Authorization error (403)"""
    def __init__(self, message: str = "Access denied"):
        super().__init__(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN
        )


class NotFoundException(BaseAPIException):
    """Resource not found (404)"""
    def __init__(self, resource: str, identifier: Any):
        super().__init__(
            message=f"{resource} not found",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"identifier": str(identifier)}
        )


class ConflictException(BaseAPIException):
    """Resource conflict (409)"""
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            details=details
        )


class RateLimitException(BaseAPIException):
    """Rate limit exceeded (429)"""
    def __init__(self, retry_after: int = 60):
        super().__init__(
            message="Rate limit exceeded",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details={"retry_after": retry_after}
        )


# ============================================
# SERVER ERRORS (5xx)
# ============================================

class DatabaseException(BaseAPIException):
    """Database error (500)"""
    def __init__(self, message: str = "Database error", details: Optional[Dict] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details
        )


class ExternalServiceException(BaseAPIException):
    """External service error (502)"""
    def __init__(self, service: str, message: str):
        super().__init__(
            message=f"{service} service error: {message}",
            status_code=status.HTTP_502_BAD_GATEWAY,
            details={"service": service}
        )


class ServiceUnavailableException(BaseAPIException):
    """Service unavailable (503)"""
    def __init__(self, message: str = "Service temporarily unavailable"):
        super().__init__(
            message=message,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )


# ============================================
# BUSINESS LOGIC EXCEPTIONS
# ============================================

class BusinessRuleException(BaseAPIException):
    """Business rule violation"""
    def __init__(self, rule: str, message: str):
        super().__init__(
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details={"rule": rule}
        )


class InsufficientBalanceException(BusinessRuleException):
    """Insufficient balance"""
    def __init__(self, required: float, available: float):
        super().__init__(
            rule="balance_check",
            message=f"Insufficient balance. Required: {required}, Available: {available}"
        )


class InvalidStateException(BusinessRuleException):
    """Invalid state transition"""
    def __init__(self, current_state: str, target_state: str):
        super().__init__(
            rule="state_transition",
            message=f"Cannot transition from {current_state} to {target_state}"
        )
2. Exception Handler Registration
python# backend/core/exception_handlers.py

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from loguru import logger
from sentry_sdk import capture_exception

from core.exceptions import BaseAPIException


def register_exception_handlers(app: FastAPI):
    """Register all exception handlers"""
    
    # ============================================
    # CUSTOM API EXCEPTIONS
    # ============================================
    
    @app.exception_handler(BaseAPIException)
    async def api_exception_handler(request: Request, exc: BaseAPIException):
        """Handle all custom API exceptions"""
        
        # Log based on severity
        if exc.status_code >= 500:
            logger.error(
                f"Server error: {exc.message}",
                extra={
                    "request_id": getattr(request.state, "request_id", None),
                    "path": request.url.path,
                    "method": request.method,
                    "status_code": exc.status_code,
                    "details": exc.details
                }
            )
            # Send to Sentry
            capture_exception(exc)
        else:
            logger.warning(
                f"Client error: {exc.message}",
                extra={
                    "request_id": getattr(request.state, "request_id", None),
                    "path": request.url.path,
                    "status_code": exc.status_code,
                    "details": exc.details
                }
            )
        
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "message": exc.message,
                    "type": type(exc).__name__,
                    "details": exc.details,
                    "request_id": getattr(request.state, "request_id", None)
                }
            }
        )
3. Try-Catch Best Practices
python# backend/services/example_service.py

from loguru import logger
from typing import Optional
from core.exceptions import (
    DatabaseException,
    NotFoundException,
    ExternalServiceException
)


class ExampleService:
    """Service with proper exception handling"""
    
    async def get_user(self, user_id: int) -> dict:
        """
        Get user by ID.
        
        Demonstrates:
        - Specific exception catching
        - Proper error propagation
        - Logging
        """
        
        try:
            # Database operation
            user = await self.db.get_user(user_id)
            
            if not user:
                raise NotFoundException("User", user_id)
            
            return user
            
        except NotFoundException:
            # Re-raise business exceptions as-is
            raise
            
        except Exception as e:
            # Log unexpected errors
            logger.exception(
                f"Failed to get user {user_id}",
                extra={"user_id": user_id}
            )
            # Wrap in appropriate exception
            raise DatabaseException(
                message=f"Failed to retrieve user: {str(e)}",
                details={"user_id": user_id}
            )
    
    async def create_user(self, data: dict) -> dict:
        """
        Create user with validation.
        
        Demonstrates:
        - Input validation
        - Transaction handling
        - Rollback on error
        """
        
        try:
            async with self.db.transaction():
                # Validate
                validated_data = self.validate_user_data(data)
                
                # Create user
                user = await self.db.create_user(validated_data)
                
                # Send welcome email
                await self.email_service.send_welcome(user["email"])
                
                logger.info(
                    "User created successfully",
                    extra={"user_id": user["id"]}
                )
                
                return user
                
        except ValidationException:
            # Business validation errors
            raise
            
        except Exception as e:
            logger.exception(
                "Failed to create user",
                extra={"data": data}
            )
            raise DatabaseException(
                message="Failed to create user",
                details={"error": str(e)}
            )
    
    async def call_external_api(self, endpoint: str) -> dict:
        """
        Call external API with retry logic.
        
        Demonstrates:
        - Retry mechanism
        - Timeout handling
        - External service errors
        """
        
        max_retries = 3
        timeout = 5.0
        
        for attempt in range(max_retries):
            try:
                response = await self.http_client.get(
                    endpoint,
                    timeout=timeout
                )
                
                if response.status_code == 200:
                    return response.json()
                
                # Non-200 status
                logger.warning(
                    f"External API returned {response.status_code}",
                    extra={
                        "endpoint": endpoint,
                        "status": response.status_code,
                        "attempt": attempt + 1
                    }
                )
                
            except TimeoutError:
                logger.warning(
                    f"External API timeout (attempt {attempt + 1}/{max_retries})",
                    extra={"endpoint": endpoint}
                )
                
                if attempt == max_retries - 1:
                    raise ExternalServiceException(
                        "External API",
                        f"Request timeout after {max_retries} attempts"
                    )
                
                # Exponential backoff
                await asyncio.sleep(2 ** attempt)
                
            except Exception as e:
                logger.exception(
                    "External API error",
                    extra={"endpoint": endpoint}
                )
                raise ExternalServiceException(
                    "External API",
                    str(e)
                )
4. Context Managers for Resource Cleanup
python# backend/utils/resource_managers.py

from contextlib import asynccontextmanager, contextmanager
from loguru import logger
import traceback


@asynccontextmanager
async def database_transaction(db):
    """
    Database transaction context manager.
    
    Usage:
        async with database_transaction(db):
            await db.execute(...)
            await db.execute(...)
    """
    try:
        await db.begin()
        logger.debug("Transaction started")
        
        yield db
        
        await db.commit()
        logger.debug("Transaction committed")
        
    except Exception as e:
        await db.rollback()
        logger.error(
            "Transaction rolled back",
            extra={"error": str(e)}
        )
        raise


@contextmanager
def file_handler(filepath: str, mode: str = 'r'):
    """
    File handler with automatic cleanup.
    
    Usage:
        with file_handler('/path/to/file.txt', 'r') as f:
            content = f.read()
    """
    file = None
    try:
        file = open(filepath, mode)
        logger.debug(f"Opened file: {filepath}")
        
        yield file
        
    except Exception as e:
        logger.error(
            f"Error handling file: {filepath}",
            extra={"error": str(e)}
        )
        raise
        
    finally:
        if file:
            file.close()
            logger.debug(f"Closed file: {filepath}")


@asynccontextmanager
async def temporary_resource(resource_name: str):
    """
    Generic temporary resource manager.
    
    Usage:
        async with temporary_resource("gpu_model"):
            # Use resource
            pass
        # Resource automatically cleaned up
    """
    try:
        # Acquire resource
        resource = await acquire_resource(resource_name)
        logger.info(f"Acquired resource: {resource_name}")
        
        yield resource
        
    except Exception as e:
        logger.error(
            f"Error with resource: {resource_name}",
            extra={"error": str(e), "traceback": traceback.format_exc()}
        )
        raise
        
    finally:
        # Always release resource
        await release_resource(resource_name)
        logger.info(f"Released resource: {resource_name}")

🔖 REQUEST ID TRACKING
1. Request ID Middleware
python# backend/middleware/request_id.py

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import uuid
from contextvars import ContextVar
from typing import Optional

# Context variable for request ID (thread-safe)
request_id_var: ContextVar[Optional[str]] = ContextVar('request_id', default=None)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware to generate and track request IDs.
    
    Features:
    - Generate UUID for each request
    - Accept X-Request-ID header if provided
    - Add request ID to response headers
    - Store in context for logging
    """
    
    async def dispatch(self, request: Request, call_next):
        """Process request and add request ID"""
        
        # Get or generate request ID
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = str(uuid.uuid4())
        
        # Store in request state
        request.state.request_id = request_id
        
        # Store in context variable (for logging)
        request_id_var.set(request_id)
        
        # Process request
        response: Response = await call_next(request)
        
        # Add to response headers
        response.headers["X-Request-ID"] = request_id
        
        return response
2. Request ID in Logging
python# backend/core/logging/request_logger.py

from loguru import logger
from contextvars import ContextVar
from typing import Optional


# Get request ID from context
def get_request_id() -> Optional[str]:
    """Get current request ID from context"""
    from middleware.request_id import request_id_var
    return request_id_var.get()


# Custom logger with request ID
class RequestLogger:
    """Logger that automatically includes request ID"""
    
    def __init__(self, name: str):
        self.name = name
    
    def _log(self, level: str, message: str, **kwargs):
        """Internal log method with request ID"""
        
        # Get request ID
        request_id = get_request_id()
        
        # Add to extra fields
        extra = kwargs.get("extra", {})
        if request_id:
            extra["request_id"] = request_id
        
        # Log with request ID
        getattr(logger, level)(
            message,
            extra=extra
        )
    
    def debug(self, message: str, **kwargs):
        self._log("debug", message, **kwargs)
    
    def info(self, message: str, **kwargs):
        self._log("info", message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        self._log("warning", message, **kwargs)
    
    def error(self, message: str, **kwargs):
        self._log("error", message, **kwargs)
    
    def critical(self, message: str, **kwargs):
        self._log("critical", message, **kwargs)


# Usage
log = RequestLogger("api")
log.info("Processing request")  # Automatically includes request_id
3. Request ID in Database Queries
python# backend/database/query_logger.py

from sqlalchemy.engine import Engine
from sqlalchemy import event
from loguru import logger
from middleware.request_id import get_request_id


def setup_query_logging(engine: Engine):
    """Setup database query logging with request IDs"""
    
    @event.listens_for(engine, "before_cursor_execute")
    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        """Log query start"""
        conn.info.setdefault("query_start_time", []).append(time.time())
        
        logger.debug(
            "SQL Query started",
            extra={
                "request_id": get_request_id(),
                "statement": statement[:200],  # Truncate long queries
                "parameters": parameters
            }
        )
    
    @event.listens_for(engine, "after_cursor_execute")
    def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        """Log query completion"""
        total_time = time.time() - conn.info["query_start_time"].pop(-1)
        
        logger.debug(
            "SQL Query completed",
            extra={
                "request_id": get_request_id(),
                "statement": statement[:200],
                "execution_time": total_time,
                "row_count": cursor.rowcount
            }
        )
4. Request Tracing Across Services
python# backend/utils/distributed_tracing.py

import httpx
from typing import Optional
from middleware.request_id import get_request_id


class TracedHTTPClient:
    """
    HTTP client that propagates request ID to downstream services.
    
    Usage:
        client = TracedHTTPClient()
        response = await client.get("https://api.example.com/users")
    """
    
    def __init__(self):
        self.client = httpx.AsyncClient()
    
    def _get_headers(self) -> dict:
        """Get headers with request ID"""
        headers = {}
        
        request_id = get_request_id()
        if request_id:
            headers["X-Request-ID"] = request_id
            headers["X-Trace-ID"] = request_id  # Alternative header name
        
        return headers
    
    async def get(self, url: str, **kwargs):
        """GET request with tracing"""
        headers = {**self._get_headers(), **kwargs.get("headers", {})}
        return await self.client.get(url, headers=headers, **kwargs)
    
    async def post(self, url: str, **kwargs):
        """POST request with tracing"""
        headers = {**self._get_headers(), **kwargs.get("headers", {})}
        return await self.client.post(url, headers=headers, **kwargs)

🔄 LOG ROTATION & MANAGEMENT
1. Loguru Rotation Configuration
python# backend/core/logging/rotation.py

from loguru import logger
from pathlib import Path
import sys


def setup_log_rotation():
    """Configure log rotation for all log files"""
    
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # ============================================
    # TIME-BASED ROTATION (Daily)
    # ============================================
    
    logger.add(
        log_dir / "app_{time:YYYY-MM-DD}.log",
        rotation="00:00",  # Rotate at midnight
        retention="30 days",  # Keep for 30 days
        compression="zip",  # Compress old logs
        serialize=True,  # JSON format
        enqueue=True,  # Async
        level="INFO"
    )
    
    # ============================================
    # SIZE-BASED ROTATION
    # ============================================
    
    logger.add(
        log_dir / "large_operations.log",
        rotation="100 MB",  # Rotate when file reaches 100 MB
        retention=10,  # Keep last 10 files
        compression="gz",
        serialize=True,
        filter=lambda record: "large_operation" in record["extra"]
    )
    
    # ============================================
    # COMBINED ROTATION (Time + Size)
    # ============================================
    
    logger.add(
        log_dir / "combined.log",
        rotation="1 week",  # Weekly OR
        # rotation="500 MB",  # when 500 MB reached
        retention="4 weeks",
        compression="zip"
    )
    
    # ============================================
    # CUSTOM ROTATION FUNCTION
    # ============================================
    
    def rotation_function(message, file):
        """
        Custom rotation logic.
        
        Return True to trigger rotation.
        """
        # Rotate if file is older than 7 days
        from datetime import datetime, timedelta
        if file.stat().st_mtime < (datetime.now() - timedelta(days=7)).timestamp():
            return True
        
        # OR if file is larger than 50 MB
        if file.stat().st_size > 50 * 1024 * 1024:
            return True
        
        return False
    
    logger.add(
        log_dir / "custom_rotation.log",
        rotation=rotation_function,
        retention=20,
        compression="bz2"
    )
2. Log Cleanup Scripts
python# scripts/cleanup_logs.py

"""
Script to clean up old log files.

Usage:
    python scripts/cleanup_logs.py --days 30
    python scripts/cleanup_logs.py --size 1GB
"""

import argparse
from pathlib import Path
from datetime import datetime, timedelta
import os
from loguru import logger


def cleanup_old_logs(log_dir: str = "logs", days: int = 30):
    """Delete log files older than specified days"""
    
    log_path = Path(log_dir)
    if not log_path.exists():
        logger.warning(f"Log directory not found: {log_dir}")
        return
    
    cutoff_date = datetime.now() - timedelta(days=days)
    deleted_count = 0
    freed_space = 0
    
    for log_file in log_path.glob("*.log*"):
        # Get file modification time
        file_time = datetime.fromtimestamp(log_file.stat().st_mtime)
        
        if file_time < cutoff_date:
            file_size = log_file.stat().st_size
            log_file.unlink()
            
            deleted_count += 1
            freed_space += file_size
            
            logger.info(
                f"Deleted old log: {log_file.name}",
                extra={
                    "age_days": (datetime.now() - file_time).days,
                    "size_mb": file_size / (1024 * 1024)
                }
            )
    
    logger.info(
        f"Cleanup complete",
        extra={
            "deleted_files": deleted_count,
            "freed_space_mb": freed_space / (1024 * 1024)
        }
    )


def cleanup_by_size(log_dir: str = "logs", max_size_gb: float = 1.0):
    """Delete oldest logs if total size exceeds limit"""
    
    log_path = Path(log_dir)
    if not log_path.exists():
        return
    
    # Get all log files with their sizes
    log_files = []
    total_size = 0
    
    for log_file in log_path.glob("*.log*"):
        size = log_file.stat().st_size
        mtime = log_file.stat().st_mtime
        
        log_files.append((log_file, size, mtime))
        total_size += size
    
    # Convert to bytes
    max_size_bytes = max_size_gb * 1024 * 1024 * 1024
    
    if total_size <= max_size_bytes:
        logger.info(
            f"Total log size within limit",
            extra={
                "total_size_gb": total_size / (1024 ** 3),
                "limit_gb": max_size_gb
            }
        )
        return
    
    # Sort by modification time (oldest first)
    log_files.sort(key=lambda x: x[2])
    
    # Delete oldest until under limit
    deleted_count = 0
    freed_space = 0
    
    for log_file, size, mtime in log_files:
        if total_size <= max_size_bytes:
            break
        
        log_file.unlink()
        total_size -= size
        freed_space += size
        deleted_count += 1
        
        logger.info(f"Deleted to free space: {log_file.name}")
    
    logger.info(
        f"Size-based cleanup complete",
        extra={
            "deleted_files": deleted_count,
            "freed_space_gb": freed_space / (1024 ** 3),
            "final_size_gb": total_size / (1024 ** 3)
        }
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clean up old log files")
    parser.add_argument("--days", type=int, help="Delete logs older than N days")
    parser.add_argument("--size", type=str, help="Keep total size under N GB (e.g., '1GB')")
    parser.add_argument("--dir", type=str, default="logs", help="Log directory")
    
    args = parser.parse_args()
    
    if args.days:
        cleanup_old_logs(args.dir, args.days)
    
    if args.size:
        # Parse size (e.g., "1GB" -> 1.0)
        size_gb = float(args.size.replace("GB", "").replace("gb", ""))
        cleanup_by_size(args.dir, size_gb)
3. Cron Job for Automatic Cleanup
bash# crontab -e

# Clean up logs older than 30 days, every day at 2 AM
0 2 * * * cd /path/to/project && python scripts/cleanup_logs.py --days 30

# Check total size weekly (Sundays at 3 AM)
0 3 * * 0 cd /path/to/project && python scripts/cleanup_logs.py --size 5GB
4. systemd Timer (Alternative to cron)
ini# /etc/systemd/system/log-cleanup.timer

[Unit]
Description=Daily log cleanup timer
Requires=log-cleanup.service

[Timer]
OnCalendar=daily
OnCalendar=02:00
Persistent=true

[Install]
WantedBy=timers.target
ini# /etc/systemd/system/log-cleanup.service

[Unit]
Description=Clean up old application logs

[Service]
Type=oneshot
User=youruser
WorkingDirectory=/path/to/project
ExecStart=/usr/bin/python3 scripts/cleanup_logs.py --days 30

[Install]
WantedBy=multi-user.target
bash# Enable and start timer
sudo systemctl enable log-cleanup.timer
sudo systemctl start log-cleanup.timer

# Check timer status
sudo systemctl list-timers

🐛 DEBUGGING STRATEGIES
1. Debug Logging Configuration
python# backend/core/logging/debug_config.py

from loguru import logger
import sys


def enable_debug_mode():
    """Enable verbose debug logging"""
    
    # Remove existing handlers
    logger.remove()
    
    # Add comprehensive debug handler
    logger.add(
        sys.stderr,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>\n"
            "{extra}"
        ),
        level="DEBUG",
        colorize=True,
        backtrace=True,  # Show full traceback
        diagnose=True,   # Show variable values
        enqueue=False    # Synchronous for debugging
    )
    
    # Add debug file
    logger.add(
        "logs/debug.log",
        format="{time} | {level} | {name}:{function}:{line} | {message}",
        level="DEBUG",
        rotation="10 MB",
        retention=3,
        diagnose=True,
        backtrace=True
    )
    
    logger.info("Debug mode enabled")


def log_function_calls(func):
    """
    Decorator to log function entry/exit with arguments.
    
    Usage:
        @log_function_calls
        def my_function(arg1, arg2):
            return arg1 + arg2
    """
    import functools
    import inspect
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # Get function signature
        sig = inspect.signature(func)
        bound_args = sig.bind(*args, **kwargs)
        bound_args.apply_defaults()
        
        # Log entry
        logger.debug(
            f"Entering {func.__name__}",
            extra={
                "function": func.__name__,
                "args": dict(bound_args.arguments)
            }
        )
        
        try:
            result = func(*args, **kwargs)
            
            # Log exit
            logger.debug(
                f"Exiting {func.__name__}",
                extra={
                    "function": func.__name__,
                    "result": str(result)[:200]  # Truncate large results
                }
            )
            
            return result
            
        except Exception as e:
            # Log exception
            logger.exception(
                f"Exception in {func.__name__}",
                extra={
                    "function": func.__name__,
                    "exception": str(e)
                }
            )
            raise
    
    return wrapper


def log_async_function_calls(func):
    """Decorator for async functions"""
    import functools
    import inspect
    
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        sig = inspect.signature(func)
        bound_args = sig.bind(*args, **kwargs)
        bound_args.apply_defaults()
        
        logger.debug(
            f"Entering async {func.__name__}",
            extra={
                "function": func.__name__,
                "args": dict(bound_args.arguments)
            }
        )
        
        try:
            result = await func(*args, **kwargs)
            
            logger.debug(
                f"Exiting async {func.__name__}",
                extra={
                    "function": func.__name__,
                    "result": str(result)[:200]
                }
            )
            
            return result
            
        except Exception as e:
            logger.exception(
                f"Exception in async {func.__name__}",
                extra={
                    "function": func.__name__,
                    "exception": str(e)
                }
            )
            raise
    
    return wrapper
2. Performance Profiling
python# backend/utils/profiling.py

import time
import functools
from loguru import logger
from typing import Callable
import cProfile
import pstats
import io


def profile_performance(func: Callable):
    """
    Decorator to profile function performance.
    
    Logs execution time and can output detailed profiling data.
    """
    
    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        start_time = time.time()
        
        try:
            result = await func(*args, **kwargs)
            elapsed = time.time() - start_time
            
            logger.info(
                f"Performance: {func.__name__}",
                extra={
                    "function": func.__name__,
                    "execution_time": elapsed,
                    "performance": True
                }
            )
            
            # Warn if slow
            if elapsed > 1.0:
                logger.warning(
                    f"Slow function detected: {func.__name__}",
                    extra={
                        "execution_time": elapsed,
                        "threshold": 1.0
                    }
                )
            
            return result
            
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(
                f"Function failed after {elapsed}s",
                extra={
                    "function": func.__name__,
                    "execution_time": elapsed,
                    "error": str(e)
                }
            )
            raise
    
    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        start_time = time.time()
        
        try:
            result = func(*args, **kwargs)
            elapsed = time.time() - start_time
            
            logger.info(
                f"Performance: {func.__name__}",
                extra={
                    "function": func.__name__,
                    "execution_time": elapsed
                }
            )
            
            return result
            
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(
                f"Function failed after {elapsed}s",
                extra={
                    "function": func.__name__,
                    "execution_time": elapsed,
                    "error": str(e)
                }
            )
            raise
    
    # Return appropriate wrapper
    import asyncio
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    else:
        return sync_wrapper


def detailed_profiler(func: Callable):
    """
    Decorator for detailed cProfile profiling.
    
    Generates profiling report and logs top functions.
    """
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        profiler = cProfile.Profile()
        profiler.enable()
        
        try:
            result = func(*args, **kwargs)
            return result
            
        finally:
            profiler.disable()
            
            # Generate report
            s = io.StringIO()
            ps = pstats.Stats(profiler, stream=s).sort_stats('cumulative')
            ps.print_stats(20)  # Top 20 functions
            
            logger.debug(
                f"Profiling report for {func.__name__}:\n{s.getvalue()}"
            )
    
    return wrapper
3. Memory Debugging
python# backend/utils/memory_debug.py

import tracemalloc
from loguru import logger
import functools


def track_memory(func):
    """
    Decorator to track memory usage of a function.
    
    Logs memory before/after and peak memory usage.
    """
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # Start tracking
        tracemalloc.start()
        
        try:
            result = func(*args, **kwargs)
            
            # Get memory stats
            current, peak = tracemalloc.get_traced_memory()
            
            logger.info(
                f"Memory usage: {func.__name__}",
                extra={
                    "function": func.__name__,
                    "current_mb": current / (1024 * 1024),
                    "peak_mb": peak / (1024 * 1024)
                }
            )
            
            # Warn if excessive
            if peak > 100 * 1024 * 1024:  # 100 MB
                logger.warning(
                    f"High memory usage: {func.__name__}",
                    extra={
                        "peak_mb": peak / (1024 * 1024),
                        "threshold_mb": 100
                    }
                )
            
            return result
            
        finally:
            tracemalloc.stop()
    
    return wrapper


def log_memory_snapshot(top_n: int = 10):
    """
    Log current memory snapshot showing top allocations.
    
    Usage:
        log_memory_snapshot(20)  # Show top 20 allocations
    """
    
    snapshot = tracemalloc.take_snapshot()
    top_stats = snapshot.statistics('lineno')
    
    logger.info(f"Top {top_n} memory allocations:")
    
    for index, stat in enumerate(top_stats[:top_n], 1):
        logger.info(
            f"#{index}: {stat.filename}:{stat.lineno}",
            extra={
                "size_mb": stat.size / (1024 * 1024),
                "count": stat.count
            }
        )
4. Interactive Debugging
python# backend/utils/debug_helpers.py

from loguru import logger
import pdb
import sys


def breakpoint_on_exception(func):
    """
    Decorator to drop into debugger on exception.
    
    Only active when DEBUG=True
    """
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if os.getenv("DEBUG", "").lower() == "true":
                logger.error(f"Exception in {func.__name__}: {e}")
                pdb.post_mortem()
            raise
    
    return wrapper


def debug_print(*args, **kwargs):
    """
    Enhanced print for debugging that includes context.
    
    Usage:
        debug_print("User ID:", user_id)
    """
    import inspect
    
    # Get caller info
    frame = inspect.currentframe().f_back
    filename = frame.f_code.co_filename
    lineno = frame.f_lineno
    function = frame.f_code.co_name
    
    # Format message
    message = " ".join(str(arg) for arg in args)
    
    logger.debug(
        message,
        extra={
            "file": filename,
            "line": lineno,
            "function": function,
            **kwargs
        }
    )

✅ PRODUCTION BEST PRACTICES
1. Production Logging Checklist
python# backend/core/logging/production_config.py

"""
PRODUCTION LOGGING CHECKLIST
============================

✅ Log Levels:
   - DEBUG: Disabled in production
   - INFO: Business events only
   - WARNING: Potential issues
   - ERROR: All errors
   - CRITICAL: System failures

✅ Performance:
   - Async logging enabled (enqueue=True)
   - Buffering for high-throughput
   - Sampling for verbose logs

✅ Security:
   - No PII in logs
   - No passwords/tokens
   - Sanitize sensitive data

✅ Rotation:
   - Time-based (daily)
   - Size-based (100MB max)
   - Retention policy (30-90 days)
   - Compression enabled

✅ Monitoring:
   - Centralized logging (ELK/Loki)
   - Error tracking (Sentry)
   - Alerting on errors
   - Dashboards (Grafana/Kibana)

✅ Structure:
   - JSON format
   - Request ID in every log
   - Consistent fields
   - Proper severity levels

✅ Cost:
   - Log size monitoring
   - Storage limits
   - Sampling high-volume logs
   - Cleanup policies
"""


def setup_production_logging():
    """Configure logging for production environment"""
    
    from loguru import logger
    import sys
    from pathlib import Path
    
    # Remove all handlers
    logger.remove()
    
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # ============================================
    # CONSOLE (Errors Only)
    # ============================================
    
    logger.add(
        sys.stderr,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
        level="ERROR",  # Only errors to console
        colorize=False,
        backtrace=False,
        diagnose=False
    )
    
    # ============================================
    # APPLICATION LOGS (JSON)
    # ============================================
    
    logger.add(
        log_dir / "app_{time:YYYY-MM-DD}.log",
        format="{message}",
        level="INFO",  # No DEBUG in production
        rotation="00:00",
        retention="30 days",
        compression="zip",
        serialize=True,  # JSON
        enqueue=True,  # Async
        backtrace=True,
        diagnose=False  # Don't expose variable values
    )
    
    # ============================================
    # ERROR LOGS (Separate File)
    # ============================================
    
    logger.add(
        log_dir / "error_{time:YYYY-MM-DD}.log",
        format="{message}",
        level="ERROR",
        rotation="00:00",
        retention="90 days",  # Keep errors longer
        compression="zip",
        serialize=True,
        enqueue=True,
        backtrace=True,
        diagnose=True  # Full details for errors
    )
    
    # ============================================
    # SAMPLING (High-Volume Logs)
    # ============================================
    
    # Sample 10% of INFO logs for high-traffic endpoints
    def should_log(record):
        """Sample logs to reduce volume"""
        import random
        
        # Always log errors
        if record["level"].no >= 40:  # ERROR or higher
            return True
        
        # Sample INFO based on endpoint
        if "high_traffic" in record["extra"]:
            return random.random() < 0.1  # 10% sampling
        
        return True
    
    logger.add(
        log_dir / "sampled_{time:YYYY-MM-DD}.log",
        format="{message}",
        level="INFO",
        filter=should_log,
        rotation="100 MB",
        retention=10,
        compression="zip",
        serialize=True,
        enqueue=True
    )
    
    logger.info("Production logging configured")
2. Security Best Practices
python# backend/core/logging/sanitizer.py

import re
from typing import Any, Dict


class LogSanitizer:
    """
    Sanitize sensitive data from logs.
    
    Removes or masks:
    - Passwords
    - API keys/tokens
    - Email addresses
    - Credit card numbers
    - Phone numbers
    - Social security numbers
    """
    
    # Patterns to detect sensitive data
    PATTERNS = {
        "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        "credit_card": r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b',
        "phone": r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
        "ssn": r'\b\d{3}-\d{2}-\d{4}\b',
        "api_key": r'\b[A-Za-z0-9]{32,}\b',  # Generic long alphanumeric
    }
    
    # Fields that should be filtered
    SENSITIVE_FIELDS = {
        "password", "passwd", "pwd",
        "secret", "token", "api_key", "apikey",
        "authorization", "auth",
        "credit_card", "creditcard", "cc",
        "ssn", "social_security",
    }
    
    @classmethod
    def sanitize_dict(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize dictionary by removing/masking sensitive fields"""
        
        sanitized = {}
        
        for key, value in data.items():
            # Check if key is sensitive
            if any(sensitive in key.lower() for sensitive in cls.SENSITIVE_FIELDS):
                sanitized[key] = "[REDACTED]"
            
            # Recursively sanitize nested dicts
            elif isinstance(value, dict):
                sanitized[key] = cls.sanitize_dict(value)
            
            # Sanitize lists
            elif isinstance(value, list):
                sanitized[key] = [
                    cls.sanitize_dict(item) if isinstance(item, dict) else item
                    for item in value
                ]
            
            # Sanitize strings
            elif isinstance(value, str):
                sanitized[key] = cls.sanitize_string(value)
            
            else:
                sanitized[key] = value
        
        return sanitized
    
    @classmethod
    def sanitize_string(cls, text: str) -> str:
        """Sanitize string by masking patterns"""
        
        result = text
        
        # Mask email addresses
        result = re.sub(
            cls.PATTERNS["email"],
            lambda m: m.group(0)[:3] + "***@***" + m.group(0)[-4:],
            result
        )
        
        # Mask credit cards
        result = re.sub(
            cls.PATTERNS["credit_card"],
            "****-****-****-****",
            result
        )
        
        # Mask phone numbers
        result = re.sub(
            cls.PATTERNS["phone"],
            "***-***-****",
            result
        )
        
        # Mask SSN
        result = re.sub(
            cls.PATTERNS["ssn"],
            "***-**-****",
            result
        )
        
        return result


# Usage
sanitizer = LogSanitizer()

user_data = {
    "username": "john_doe",
    "email": "john@example.com",
    "password": "super_secret",
    "credit_card": "1234-5678-9012-3456"
}

safe_data = sanitizer.sanitize_dict(user_data)
logger.info("User data", extra=safe_data)
# Result: { "username": "john_doe", "email": "joh***@***m.com", "password": "[REDACTED]", "credit_card": "****-****-****-****" }
3. Cost Optimization
python# backend/core/logging/cost_optimizer.py

"""
LOG COST OPTIMIZATION STRATEGIES
================================

1. SAMPLING
   - Sample high-volume logs (10-20%)
   - Always log errors (100%)
   - Strategic sampling by endpoint

2. RETENTION
   - INFO logs: 7-30 days
   - ERROR logs: 90 days
   - AUDIT logs: 1-7 years (compliance)

3. COMPRESSION
   - gzip/bzip2 for old logs
   - 70-90% size reduction

4. STORAGE TIERS
   - Hot: Last 7 days (fast access)
   - Warm: 8-30 days (slower)
   - Cold: 30+ days (archive)

5. LOG LEVELS
   - Production: INFO and above
   - Staging: DEBUG for 24h after deploy
   - Development: All levels

6. STRUCTURED LOGGING
   - JSON for parsing
   - Remove redundant fields
   - Compress field names

7. ASYNC LOGGING
   - Non-blocking
   - Batched writes
   - Better performance
"""


class CostOptimizedLogger:
    """Logger with cost optimization features"""
    
    def __init__(self):
        self.log_count = 0
        self.bytes_logged = 0
    
    def should_sample(self, level: str, endpoint: str = None) -> bool:
        """Determine if log should be sampled"""
        
        # Always log errors
        if level in ("ERROR", "CRITICAL"):
            return True
        
        # High-traffic endpoints: 10% sampling
        high_traffic = ["/health", "/metrics", "/status"]
        if endpoint in high_traffic:
            return random.random() < 0.1
        
        # Normal endpoints: 50% sampling for DEBUG
        if level == "DEBUG":
            return random.random() < 0.5
        
        # Always log INFO, WARNING
        return True
    
    def log_with_budget(self, level: str, message: str, **kwargs):
        """Log with budget tracking"""
        
        # Check if should sample
        endpoint = kwargs.get("extra", {}).get("endpoint")
        if not self.should_sample(level, endpoint):
            return
        
        # Estimate log size
        log_size = len(message) + len(str(kwargs))
        
        # Track metrics
        self.log_count += 1
        self.bytes_logged += log_size
        
        # Warn if budget exceeded
        daily_budget_mb = 100  # 100 MB per day
        if self.bytes_logged > daily_budget_mb * 1024 * 1024:
            logger.warning(
                "Daily log budget exceeded",
                extra={
                    "bytes_logged": self.bytes_logged,
                    "budget_mb": daily_budget_mb
                }
            )
        
        # Log normally
        getattr(logger, level.lower())(message, **kwargs)

🎯 SUMMARY & NEXT STEPS
Quick Reference
python# ============================================
# IMPORT EVERYTHING
# ============================================

from loguru import logger
from core.logging.loguru_config import LoguruConfig
from core.sentry.config import init_sentry
from core.exceptions import *
from middleware.request_id import RequestIDMiddleware

# ============================================
# SETUP (in main.py)
# ============================================

# 1. Configure logging
LoguruConfig.setup()

# 2. Initialize Sentry
init_sentry(
    dsn=os.getenv("SENTRY_DSN"),
    environment="production"
)

# 3. Add middleware
app.add_middleware(RequestIDMiddleware)

# 4. Register exception handlers
from core.exception_handlers import register_exception_handlers
register_exception_handlers(app)

# ============================================
# USAGE
# ============================================

# Simple logging
logger.info("User logged in", extra={"user_id": 123})

# Exception handling
try:
    result = await some_operation()
except Exception as e:
    logger.exception("Operation failed")
    raise DatabaseException("Failed to process")

# Context
with log_context(user_id=123):
    logger.info("Processing")  # Automatically includes user_id

# Performance tracking
with log_execution_time("database_query"):
    result = await db.query()
