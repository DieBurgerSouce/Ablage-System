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