🔄 BACKGROUND TASKS & QUEUE MANAGEMENT
Comprehensive Guide to Celery with FastAPI

📋 TABLE OF CONTENTS

Introduction
Celery Setup & Configuration
Redis as Message Broker
Task Definition & Scheduling
Retry Logic & Error Handling
Task Monitoring with Flower
Periodic Tasks (Celery Beat)
Task Priorities
Distributed Task Processing
Best Practices


🎯 INTRODUCTION
What is Celery?
Celery is a distributed task queue that allows you to run time-consuming operations asynchronously in the background, freeing up your API to handle more requests.
Use Cases
┌─────────────────────────────────────────────────────────┐
│                    CELERY USE CASES                     │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ✅ OCR Processing (Long-running)                       │
│  ✅ Email/SMS Sending (I/O bound)                       │
│  ✅ Report Generation (CPU intensive)                   │
│  ✅ Data Import/Export (Batch operations)               │
│  ✅ Image/Video Processing (Media tasks)                │
│  ✅ Web Scraping (External API calls)                   │
│  ✅ Database Cleanup (Scheduled maintenance)            │
│  ✅ Notifications (Real-time alerts)                    │
│                                                         │
└─────────────────────────────────────────────────────────┘
Architecture Overview
┌──────────────┐         ┌──────────────┐         ┌──────────────┐
│   FastAPI    │────────▶│    Redis     │◀────────│    Celery    │
│   Backend    │  Tasks  │   (Broker)   │  Tasks  │   Workers    │
└──────────────┘         └──────────────┘         └──────────────┘
       │                        │                         │
       │                        │                         │
       ▼                        ▼                         ▼
┌──────────────┐         ┌──────────────┐         ┌──────────────┐
│  PostgreSQL  │         │   Celery     │         │   Flower     │
│  (Results)   │         │   Backend    │         │ (Monitoring) │
└──────────────┘         └──────────────┘         └──────────────┘

🛠️ CELERY SETUP & CONFIGURATION
1. Installation
bash# requirements.txt

# Celery with Redis support
celery[redis]==5.3.4

# Redis client
redis==5.0.1

# Flower for monitoring
flower==2.0.1

# Additional dependencies
kombu==5.3.4  # Messaging library
billiard==4.2.0  # Multiprocessing library
vine==5.1.0  # Promises/callbacks
bash# Install dependencies
pip install -r requirements.txt
```

### 2. Project Structure
```
backend/
├── celery_app/
│   ├── __init__.py
│   ├── celery.py           # Celery app configuration
│   ├── config.py           # Celery settings
│   └── tasks/
│       ├── __init__.py
│       ├── ocr_tasks.py    # OCR processing tasks
│       ├── email_tasks.py  # Email sending tasks
│       ├── report_tasks.py # Report generation
│       └── cleanup_tasks.py # Maintenance tasks
│
├── core/
│   └── config.py           # App settings
│
└── main.py
3. Celery Configuration
python# backend/celery_app/config.py

from kombu import Exchange, Queue
from datetime import timedelta


class CeleryConfig:
    """
    Celery configuration.
    
    Documentation: https://docs.celeryq.dev/en/stable/userguide/configuration.html
    """
    
    # ============================================
    # BROKER SETTINGS
    # ============================================
    
    # Redis as message broker
    broker_url = "redis://localhost:6379/0"
    
    # Connection settings
    broker_connection_retry_on_startup = True
    broker_connection_retry = True
    broker_connection_max_retries = 10
    
    # Broker pool limit
    broker_pool_limit = 10
    
    # ============================================
    # RESULT BACKEND SETTINGS
    # ============================================
    
    # Store results in Redis
    result_backend = "redis://localhost:6379/1"
    
    # Result expiration (1 day)
    result_expires = 86400
    
    # Store extended task info
    result_extended = True
    
    # Backend settings
    result_backend_transport_options = {
        'retry_policy': {
            'timeout': 5.0
        }
    }
    
    # ============================================
    # TASK SETTINGS
    # ============================================
    
    # Task serializer
    task_serializer = "json"
    accept_content = ["json"]
    result_serializer = "json"
    
    # Timezone
    timezone = "UTC"
    enable_utc = True
    
    # Task time limits
    task_soft_time_limit = 300  # 5 minutes (soft limit)
    task_time_limit = 600  # 10 minutes (hard limit)
    
    # Task acknowledgment
    task_acks_late = True  # Acknowledge after task completes
    task_reject_on_worker_lost = True
    
    # Task result settings
    task_ignore_result = False
    task_store_errors_even_if_ignored = True
    
    # Task compression
    task_compression = "gzip"
    result_compression = "gzip"
    
    # Task execution settings
    task_eager_propagates = True  # Propagate exceptions in eager mode
    
    # ============================================
    # WORKER SETTINGS
    # ============================================
    
    # Worker concurrency
    worker_prefetch_multiplier = 4  # Tasks to prefetch per worker
    worker_max_tasks_per_child = 1000  # Restart worker after N tasks
    
    # Worker optimization
    worker_disable_rate_limits = False
    
    # Worker events
    worker_send_task_events = True
    task_send_sent_event = True
    
    # ============================================
    # QUEUE SETTINGS
    # ============================================
    
    # Default queue
    task_default_queue = "default"
    task_default_exchange = "default"
    task_default_routing_key = "default"
    
    # Queue definitions
    task_queues = (
        # High priority queue
        Queue(
            "high_priority",
            Exchange("high_priority"),
            routing_key="high_priority",
            priority=10
        ),
        
        # Default queue
        Queue(
            "default",
            Exchange("default"),
            routing_key="default",
            priority=5
        ),
        
        # Low priority queue (reports, cleanup)
        Queue(
            "low_priority",
            Exchange("low_priority"),
            routing_key="low_priority",
            priority=1
        ),
        
        # OCR processing queue
        Queue(
            "ocr",
            Exchange("ocr"),
            routing_key="ocr",
            priority=7
        ),
        
        # Email queue
        Queue(
            "email",
            Exchange("email"),
            routing_key="email",
            priority=8
        ),
    )
    
    # Task routing
    task_routes = {
        "celery_app.tasks.ocr_tasks.*": {
            "queue": "ocr",
            "routing_key": "ocr"
        },
        "celery_app.tasks.email_tasks.*": {
            "queue": "email",
            "routing_key": "email"
        },
        "celery_app.tasks.report_tasks.*": {
            "queue": "low_priority",
            "routing_key": "low_priority"
        },
        "celery_app.tasks.cleanup_tasks.*": {
            "queue": "low_priority",
            "routing_key": "low_priority"
        },
    }
    
    # ============================================
    # BEAT SCHEDULE (Periodic Tasks)
    # ============================================
    
    beat_schedule = {
        # Clean up old files every day at 2 AM
        "cleanup-old-files": {
            "task": "celery_app.tasks.cleanup_tasks.cleanup_old_files",
            "schedule": timedelta(days=1),
            "options": {"queue": "low_priority"}
        },
        
        # Generate daily reports at 8 AM
        "generate-daily-report": {
            "task": "celery_app.tasks.report_tasks.generate_daily_report",
            "schedule": timedelta(days=1),
            "options": {"queue": "low_priority"}
        },
        
        # Health check every 5 minutes
        "health-check": {
            "task": "celery_app.tasks.cleanup_tasks.health_check",
            "schedule": timedelta(minutes=5),
        },
    }
    
    # ============================================
    # MONITORING & LOGGING
    # ============================================
    
    # Task events
    worker_send_task_events = True
    task_send_sent_event = True
    
    # Logging
    worker_log_format = "[%(asctime)s: %(levelname)s/%(processName)s] %(message)s"
    worker_task_log_format = "[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s"


# For development
class CeleryConfigDev(CeleryConfig):
    """Development configuration"""
    
    task_always_eager = False  # Set to True to run tasks synchronously
    task_eager_propagates = True


# For production
class CeleryConfigProd(CeleryConfig):
    """Production configuration"""
    
    # Use different Redis instance for production
    broker_url = "redis://prod-redis:6379/0"
    result_backend = "redis://prod-redis:6379/1"
    
    # Production optimizations
    worker_prefetch_multiplier = 8
    worker_max_tasks_per_child = 5000
4. Celery App Initialization
python# backend/celery_app/celery.py

from celery import Celery
from celery.signals import task_prerun, task_postrun, task_failure
import logging

from core.config import settings
from celery_app.config import CeleryConfig, CeleryConfigDev, CeleryConfigProd


logger = logging.getLogger(__name__)


def get_celery_config():
    """Get Celery config based on environment"""
    if settings.ENVIRONMENT == "production":
        return CeleryConfigProd
    else:
        return CeleryConfigDev


# Create Celery app
celery_app = Celery("ocr_backend")

# Load configuration
celery_app.config_from_object(get_celery_config())

# Auto-discover tasks in tasks module
celery_app.autodiscover_tasks([
    "celery_app.tasks.ocr_tasks",
    "celery_app.tasks.email_tasks",
    "celery_app.tasks.report_tasks",
    "celery_app.tasks.cleanup_tasks",
])


# ============================================
# CELERY SIGNALS
# ============================================

@task_prerun.connect
def task_prerun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, **extra):
    """
    Signal handler called before task execution.
    
    Use for:
    - Logging task start
    - Setting up resources
    - Metrics
    """
    logger.info(
        f"Task {task.name}[{task_id}] starting with args={args}, kwargs={kwargs}"
    )


@task_postrun.connect
def task_postrun_handler(
    sender=None,
    task_id=None,
    task=None,
    args=None,
    kwargs=None,
    retval=None,
    state=None,
    **extra
):
    """
    Signal handler called after task execution.
    
    Use for:
    - Logging task completion
    - Cleanup
    - Metrics
    """
    logger.info(
        f"Task {task.name}[{task_id}] completed with state={state}"
    )


@task_failure.connect
def task_failure_handler(
    sender=None,
    task_id=None,
    exception=None,
    args=None,
    kwargs=None,
    traceback=None,
    einfo=None,
    **extra
):
    """
    Signal handler called on task failure.
    
    Use for:
    - Error logging
    - Alerting
    - Cleanup
    """
    logger.error(
        f"Task {sender.name}[{task_id}] failed: {exception}\n"
        f"Args: {args}\n"
        f"Kwargs: {kwargs}\n"
        f"Traceback: {traceback}"
    )
    
    # Send alert (e.g., Sentry, email)
    # send_error_alert(task_id, exception)
5. Celery App Module
python# backend/celery_app/__init__.py

from celery_app.celery import celery_app

__all__ = ["celery_app"]

🔴 REDIS AS MESSAGE BROKER
1. Redis Installation & Setup
bash# Install Redis (Ubuntu/Debian)
sudo apt-get update
sudo apt-get install redis-server

# Start Redis
sudo systemctl start redis-server
sudo systemctl enable redis-server

# Check status
sudo systemctl status redis-server

# Test connection
redis-cli ping
# Should return: PONG
2. Docker Redis Setup
yaml# docker-compose.yml

version: '3.8'

services:
  redis:
    image: redis:7-alpine
    container_name: ocr_redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - ocr_network
  
  redis-commander:
    image: rediscommander/redis-commander:latest
    container_name: redis_commander
    environment:
      - REDIS_HOSTS=local:redis:6379
    ports:
      - "8081:8081"
    depends_on:
      - redis
    networks:
      - ocr_network

volumes:
  redis_data:

networks:
  ocr_network:
    driver: bridge
bash# Start Redis with Docker
docker-compose up -d redis

# View Redis Commander (Web UI)
# Open: http://localhost:8081
3. Redis Configuration
conf# redis.conf

# Network
bind 127.0.0.1
port 6379
timeout 0
tcp-keepalive 300

# Memory
maxmemory 256mb
maxmemory-policy allkeys-lru

# Persistence
save 900 1      # Save after 900 sec if 1 key changed
save 300 10     # Save after 300 sec if 10 keys changed
save 60 10000   # Save after 60 sec if 10000 keys changed

appendonly yes
appendfilename "appendonly.aof"

# Logging
loglevel notice
logfile /var/log/redis/redis-server.log

# Performance
databases 16
4. Redis Client Wrapper
python# backend/core/redis_client.py

import redis
from typing import Optional, Any
import json
import pickle
from datetime import timedelta
import logging

from core.config import settings


logger = logging.getLogger(__name__)


class RedisClient:
    """
    Redis client wrapper with common operations.
    
    Features:
    - Connection pooling
    - JSON serialization
    - Error handling
    - Type hints
    """
    
    def __init__(self, url: Optional[str] = None):
        """Initialize Redis client"""
        self.url = url or settings.REDIS_URL
        
        # Create connection pool
        self.pool = redis.ConnectionPool.from_url(
            self.url,
            max_connections=50,
            decode_responses=False  # For binary data support
        )
        
        self.client = redis.Redis(connection_pool=self.pool)
        
        # Test connection
        try:
            self.client.ping()
            logger.info("Redis connection established")
        except redis.ConnectionError as e:
            logger.error(f"Redis connection failed: {e}")
            raise
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get value from Redis"""
        try:
            value = self.client.get(key)
            if value is None:
                return default
            
            # Try to deserialize JSON
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                # Return raw value if not JSON
                return value
        
        except redis.RedisError as e:
            logger.error(f"Redis GET error for key '{key}': {e}")
            return default
    
    def set(
        self,
        key: str,
        value: Any,
        expire: Optional[int] = None,
        nx: bool = False,
        xx: bool = False
    ) -> bool:
        """
        Set value in Redis.
        
        Args:
            key: Redis key
            value: Value to store
            expire: Expiration in seconds
            nx: Only set if key doesn't exist
            xx: Only set if key exists
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Serialize value
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            elif not isinstance(value, (str, bytes, int, float)):
                value = pickle.dumps(value)
            
            # Set value
            return self.client.set(
                key,
                value,
                ex=expire,
                nx=nx,
                xx=xx
            )
        
        except redis.RedisError as e:
            logger.error(f"Redis SET error for key '{key}': {e}")
            return False
    
    def delete(self, *keys: str) -> int:
        """Delete keys from Redis"""
        try:
            return self.client.delete(*keys)
        except redis.RedisError as e:
            logger.error(f"Redis DELETE error: {e}")
            return 0
    
    def exists(self, *keys: str) -> int:
        """Check if keys exist"""
        try:
            return self.client.exists(*keys)
        except redis.RedisError as e:
            logger.error(f"Redis EXISTS error: {e}")
            return 0
    
    def expire(self, key: str, seconds: int) -> bool:
        """Set expiration on key"""
        try:
            return self.client.expire(key, seconds)
        except redis.RedisError as e:
            logger.error(f"Redis EXPIRE error for key '{key}': {e}")
            return False
    
    def incr(self, key: str, amount: int = 1) -> int:
        """Increment key value"""
        try:
            return self.client.incr(key, amount)
        except redis.RedisError as e:
            logger.error(f"Redis INCR error for key '{key}': {e}")
            return 0
    
    def decr(self, key: str, amount: int = 1) -> int:
        """Decrement key value"""
        try:
            return self.client.decr(key, amount)
        except redis.RedisError as e:
            logger.error(f"Redis DECR error for key '{key}': {e}")
            return 0
    
    # List operations
    def lpush(self, key: str, *values: Any) -> int:
        """Push values to list (left)"""
        try:
            serialized = [
                json.dumps(v) if isinstance(v, (dict, list)) else v
                for v in values
            ]
            return self.client.lpush(key, *serialized)
        except redis.RedisError as e:
            logger.error(f"Redis LPUSH error for key '{key}': {e}")
            return 0
    
    def rpush(self, key: str, *values: Any) -> int:
        """Push values to list (right)"""
        try:
            serialized = [
                json.dumps(v) if isinstance(v, (dict, list)) else v
                for v in values
            ]
            return self.client.rpush(key, *serialized)
        except redis.RedisError as e:
            logger.error(f"Redis RPUSH error for key '{key}': {e}")
            return 0
    
    def lrange(self, key: str, start: int = 0, end: int = -1) -> list:
        """Get list range"""
        try:
            values = self.client.lrange(key, start, end)
            return [
                json.loads(v) if v.startswith(b'{') or v.startswith(b'[') else v
                for v in values
            ]
        except redis.RedisError as e:
            logger.error(f"Redis LRANGE error for key '{key}': {e}")
            return []
    
    # Hash operations
    def hset(self, name: str, key: str, value: Any) -> int:
        """Set hash field"""
        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            return self.client.hset(name, key, value)
        except redis.RedisError as e:
            logger.error(f"Redis HSET error: {e}")
            return 0
    
    def hget(self, name: str, key: str) -> Any:
        """Get hash field"""
        try:
            value = self.client.hget(name, key)
            if value is None:
                return None
            
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
        
        except redis.RedisError as e:
            logger.error(f"Redis HGET error: {e}")
            return None
    
    def hgetall(self, name: str) -> dict:
        """Get all hash fields"""
        try:
            data = self.client.hgetall(name)
            return {
                k.decode(): (
                    json.loads(v) if v.startswith(b'{') or v.startswith(b'[')
                    else v.decode()
                )
                for k, v in data.items()
            }
        except redis.RedisError as e:
            logger.error(f"Redis HGETALL error: {e}")
            return {}
    
    # Set operations
    def sadd(self, key: str, *values: Any) -> int:
        """Add to set"""
        try:
            return self.client.sadd(key, *values)
        except redis.RedisError as e:
            logger.error(f"Redis SADD error: {e}")
            return 0
    
    def smembers(self, key: str) -> set:
        """Get set members"""
        try:
            return self.client.smembers(key)
        except redis.RedisError as e:
            logger.error(f"Redis SMEMBERS error: {e}")
            return set()
    
    # Utility methods
    def keys(self, pattern: str = "*") -> list:
        """Get keys matching pattern"""
        try:
            return [k.decode() for k in self.client.keys(pattern)]
        except redis.RedisError as e:
            logger.error(f"Redis KEYS error: {e}")
            return []
    
    def flushdb(self) -> bool:
        """Flush current database (use with caution!)"""
        try:
            return self.client.flushdb()
        except redis.RedisError as e:
            logger.error(f"Redis FLUSHDB error: {e}")
            return False
    
    def ping(self) -> bool:
        """Ping Redis"""
        try:
            return self.client.ping()
        except redis.RedisError as e:
            logger.error(f"Redis PING error: {e}")
            return False
    
    def close(self):
        """Close Redis connection"""
        self.client.close()


# Global Redis client
redis_client = RedisClient()


# Cache decorator
def cache(expire: int = 3600, key_prefix: str = "cache"):
    """
    Cache decorator for functions.
    
    Usage:
        @cache(expire=300)
        def expensive_function(arg1, arg2):
            ...
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Create cache key
            import hashlib
            key_parts = [key_prefix, func.__name__]
            key_parts.extend(str(a) for a in args)
            key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
            
            cache_key = hashlib.md5(
                ":".join(key_parts).encode()
            ).hexdigest()
            
            # Try to get from cache
            cached = redis_client.get(cache_key)
            if cached is not None:
                return cached
            
            # Execute function
            result = func(*args, **kwargs)
            
            # Store in cache
            redis_client.set(cache_key, result, expire=expire)
            
            return result
        
        return wrapper
    return decorator

📝 TASK DEFINITION & SCHEDULING
1. Basic Task Definition
python# backend/celery_app/tasks/ocr_tasks.py

from celery import Task
from celery_app.celery import celery_app
from sqlalchemy.orm import Session
import logging
from datetime import datetime

from database import SessionLocal
from models.documents import Document
from core.ocr import OCRProcessor


logger = logging.getLogger(__name__)


class DatabaseTask(Task):
    """
    Base task with database session management.
    
    Automatically handles:
    - Database session creation
    - Session cleanup
    - Error rollback
    """
    
    _db: Session = None
    
    @property
    def db(self) -> Session:
        """Get database session"""
        if self._db is None:
            self._db = SessionLocal()
        return self._db
    
    def after_return(self, *args, **kwargs):
        """Close database session after task completes"""
        if self._db is not None:
            self._db.close()
            self._db = None


@celery_app.task(
    bind=True,
    base=DatabaseTask,
    name="celery_app.tasks.ocr_tasks.process_document_ocr",
    max_retries=3,
    default_retry_delay=60  # 1 minute
)
def process_document_ocr(self, document_id: str, backend: str = "deepseek"):
    """
    Process document with OCR.
    
    Args:
        document_id: UUID of document to process
        backend: OCR backend to use (deepseek, tesseract)
    
    Returns:
        dict with OCR results
    """
    logger.info(f"Starting OCR processing for document {document_id}")
    
    try:
        # Get document
        document = self.db.query(Document).filter(
            Document.id == document_id
        ).first()
        
        if not document:
            raise ValueError(f"Document {document_id} not found")
        
        # Update status
        document.status = "processing"
        document.processing_started_at = datetime.utcnow()
        self.db.commit()
        
        # Process OCR
        ocr_processor = OCRProcessor(backend=backend)
        result = ocr_processor.process_document(document.file_path)
        
        # Update document with results
        document.status = "completed"
        document.ocr_result = result
        document.ocr_confidence = result.get("confidence", 0.0)
        document.processing_completed_at = datetime.utcnow()
        
        self.db.commit()
        
        logger.info(
            f"OCR processing completed for document {document_id}. "
            f"Confidence: {result.get('confidence', 0.0):.2f}"
        )
        
        return {
            "status": "success",
            "document_id": str(document_id),
            "confidence": result.get("confidence", 0.0)
        }
    
    except Exception as exc:
        logger.error(f"OCR processing failed for document {document_id}: {exc}")
        
        # Update document status
        if 'document' in locals():
            document.status = "failed"
            document.error_message = str(exc)
            self.db.commit()
        
        # Retry task
        raise self.retry(exc=exc)


@celery_app.task(name="celery_app.tasks.ocr_tasks.batch_process_documents")
def batch_process_documents(document_ids: list[str], backend: str = "deepseek"):
    """
    Process multiple documents in batch.
    
    Args:
        document_ids: List of document IDs
        backend: OCR backend to use
    
    Returns:
        dict with batch processing results
    """
    logger.info(f"Starting batch OCR processing for {len(document_ids)} documents")
    
    results = []
    
    for document_id in document_ids:
        # Queue individual task
        result = process_document_ocr.delay(document_id, backend)
        results.append({
            "document_id": document_id,
            "task_id": result.id
        })
    
    return {
        "status": "queued",
        "total_documents": len(document_ids),
        "tasks": results
    }


@celery_app.task(
    name="celery_app.tasks.ocr_tasks.extract_invoice_data",
    bind=True
)
def extract_invoice_data(self, document_id: str):
    """
    Extract structured data from invoice.
    
    Specialized task for invoice processing with entity extraction.
    """
    logger.info(f"Extracting invoice data from document {document_id}")
    
    db = SessionLocal()
    
    try:
        # Get document
        document = db.query(Document).filter(
            Document.id == document_id
        ).first()
        
        if not document or not document.ocr_result:
            raise ValueError(f"Document {document_id} not processed")
        
        # Extract entities from OCR result
        from core.entity_extractor import InvoiceExtractor
        
        extractor = InvoiceExtractor()
        entities = extractor.extract(document.ocr_result.get("text", ""))
        
        # Update document
        document.extracted_data = entities
        db.commit()
        
        logger.info(f"Invoice data extracted: {len(entities)} entities found")
        
        return {
            "status": "success",
            "document_id": str(document_id),
            "entities": entities
        }
    
    except Exception as exc:
        logger.error(f"Invoice extraction failed: {exc}")
        raise self.retry(exc=exc, max_retries=2)
    
    finally:
        db.close()
2. Email Tasks
python# backend/celery_app/tasks/email_tasks.py

from celery_app.celery import celery_app
from celery import group
import logging
from typing import List, Dict, Any

from core.email import EmailService


logger = logging.getLogger(__name__)


@celery_app.task(
    name="celery_app.tasks.email_tasks.send_email",
    bind=True,
    max_retries=5,
    default_retry_delay=300  # 5 minutes
)
def send_email(
    self,
    to: str,
    subject: str,
    body: str,
    html: bool = False,
    attachments: List[Dict[str, Any]] = None
):
    """
    Send email.
    
    Args:
        to: Recipient email
        subject: Email subject
        body: Email body
        html: Whether body is HTML
        attachments: List of attachments
    
    Raises:
        Retry on temporary failures
    """
    logger.info(f"Sending email to {to}: {subject}")
    
    try:
        email_service = EmailService()
        
        email_service.send(
            to=to,
            subject=subject,
            body=body,
            html=html,
            attachments=attachments or []
        )
        
        logger.info(f"Email sent successfully to {to}")
        
        return {"status": "sent", "recipient": to}
    
    except Exception as exc:
        logger.error(f"Failed to send email to {to}: {exc}")
        
        # Retry with exponential backoff
        raise self.retry(
            exc=exc,
            countdown=min(60 * (2 ** self.request.retries), 3600)  # Max 1 hour
        )


@celery_app.task(name="celery_app.tasks.email_tasks.send_verification_email")
def send_verification_email(user_email: str, verification_token: str):
    """Send email verification"""
    verification_url = f"https://app.example.com/verify?token={verification_token}"
    
    html_body = f"""
    <html>
        <body>
            <h2>Verify Your Email</h2>
            <p>Click the link below to verify your email address:</p>
            <a href="{verification_url}">Verify Email</a>
            <p>This link will expire in 24 hours.</p>
        </body>
    </html>
    """
    
    return send_email.delay(
        to=user_email,
        subject="Verify Your Email",
        body=html_body,
        html=True
    )


@celery_app.task(name="celery_app.tasks.email_tasks.send_password_reset_email")
def send_password_reset_email(user_email: str, reset_token: str):
    """Send password reset email"""
    reset_url = f"https://app.example.com/reset-password?token={reset_token}"
    
    html_body = f"""
    <html>
        <body>
            <h2>Reset Your Password</h2>
            <p>Click the link below to reset your password:</p>
            <a href="{reset_url}">Reset Password</a>
            <p>This link will expire in 1 hour.</p>
        </body>
    </html>
    """
    
    return send_email.delay(
        to=user_email,
        subject="Reset Your Password",
        body=html_body,
        html=True
    )


@celery_app.task(name="celery_app.tasks.email_tasks.send_bulk_emails")
def send_bulk_emails(recipients: List[str], subject: str, body: str):
    """
    Send bulk emails using Celery groups.
    
    Sends emails in parallel for better performance.
    """
    logger.info(f"Sending bulk emails to {len(recipients)} recipients")
    
    # Create group of email tasks
    job = group(
        send_email.s(recipient, subject, body, html=True)
        for recipient in recipients
    )
    
    # Execute group
    result = job.apply_async()
    
    return {
        "status": "queued",
        "total_emails": len(recipients),
        "group_id": result.id
    }
3. Report Generation Tasks
python# backend/celery_app/tasks/report_tasks.py

from celery_app.celery import celery_app
from celery import chain, chord
import logging
from datetime import datetime, timedelta
from typing import Dict, Any

from database import SessionLocal
from models.documents import Document
from core.reports import ReportGenerator


logger = logging.getLogger(__name__)


@celery_app.task(
    name="celery_app.tasks.report_tasks.generate_user_report",
    bind=True
)
def generate_user_report(self, user_id: str, start_date: str, end_date: str):
    """
    Generate user activity report.
    
    Args:
        user_id: User ID
        start_date: Start date (ISO format)
        end_date: End date (ISO format)
    """
    logger.info(f"Generating report for user {user_id}")
    
    db = SessionLocal()
    
    try:
        # Parse dates
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)
        
        # Get user documents
        documents = db.query(Document).filter(
            Document.user_id == user_id,
            Document.created_at >= start,
            Document.created_at <= end
        ).all()
        
        # Generate report
        report_generator = ReportGenerator()
        report_data = report_generator.generate_user_report(
            user_id=user_id,
            documents=documents,
            start_date=start,
            end_date=end
        )
        
        # Save report
        report_path = report_generator.save_report(report_data, user_id)
        
        logger.info(f"Report generated: {report_path}")
        
        return {
            "status": "completed",
            "user_id": user_id,
            "report_path": report_path,
            "total_documents": len(documents)
        }
    
    except Exception as exc:
        logger.error(f"Report generation failed: {exc}")
        raise self.retry(exc=exc)
    
    finally:
        db.close()


@celery_app.task(name="celery_app.tasks.report_tasks.generate_daily_report")
def generate_daily_report():
    """
    Generate daily system report.
    
    Runs daily via Celery Beat.
    """
    logger.info("Generating daily report")
    
    db = SessionLocal()
    
    try:
        # Get yesterday's date
        yesterday = datetime.utcnow() - timedelta(days=1)
        start = yesterday.replace(hour=0, minute=0, second=0)
        end = yesterday.replace(hour=23, minute=59, second=59)
        
        # Count documents processed
        total_documents = db.query(Document).filter(
            Document.created_at >= start,
            Document.created_at <= end
        ).count()
        
        completed = db.query(Document).filter(
            Document.created_at >= start,
            Document.created_at <= end,
            Document.status == "completed"
        ).count()
        
        failed = db.query(Document).filter(
            Document.created_at >= start,
            Document.created_at <= end,
            Document.status == "failed"
        ).count()
        
        # Create report
        report = {
            "date": yesterday.strftime("%Y-%m-%d"),
            "total_documents": total_documents,
            "completed": completed,
            "failed": failed,
            "success_rate": (completed / total_documents * 100) if total_documents > 0 else 0
        }
        
        logger.info(f"Daily report: {report}")
        
        # Send report email to admins
        from celery_app.tasks.email_tasks import send_email
        
        send_email.delay(
            to="admin@example.com",
            subject=f"Daily Report - {report['date']}",
            body=f"Documents processed: {total_documents}\n"
                 f"Completed: {completed}\n"
                 f"Failed: {failed}\n"
                 f"Success rate: {report['success_rate']:.2f}%",
            html=False
        )
        
        return report
    
    finally:
        db.close()


@celery_app.task(name="celery_app.tasks.report_tasks.aggregate_statistics")
def aggregate_statistics(period: str = "monthly"):
    """
    Aggregate statistics for a period.
    
    Used in workflow chains.
    """
    logger.info(f"Aggregating {period} statistics")
    
    # Aggregation logic
    # ...
    
    return {"period": period, "stats": {}}


# Workflow example using chain
@celery_app.task(name="celery_app.tasks.report_tasks.create_monthly_report")
def create_monthly_report():
    """
    Create monthly report using chain workflow.
    
    Steps:
    1. Aggregate statistics
    2. Generate report
    3. Send email
    """
    from celery_app.tasks.email_tasks import send_email
    
    # Create workflow
    workflow = chain(
        aggregate_statistics.s(period="monthly"),
        generate_user_report.s(user_id="admin", start_date="...", end_date="..."),
        send_email.s(to="admin@example.com", subject="Monthly Report")
    )
    
    # Execute
    result = workflow.apply_async()
    
    return {"workflow_id": result.id}



🔄 BACKGROUND TASKS & QUEUE MANAGEMENT - TEIL 2
Retry Logic, Monitoring, Periodic Tasks & Advanced Features

🔁 RETRY LOGIC & ERROR HANDLING
1. Advanced Retry Strategies
python# backend/celery_app/tasks/retry_strategies.py

from celery import Task
from celery.exceptions import Reject, Retry
from celery_app.celery import celery_app
import logging
from datetime import datetime
from typing import Optional, Type
import random


logger = logging.getLogger(__name__)


class SmartRetryTask(Task):
    """
    Base task with intelligent retry logic.
    
    Features:
    - Exponential backoff
    - Jitter for avoiding thundering herd
    - Custom retry conditions
    - Error classification
    """
    
    autoretry_for = (Exception,)
    retry_kwargs = {'max_retries': 5}
    retry_backoff = True
    retry_backoff_max = 600  # Max 10 minutes
    retry_jitter = True
    
    def retry(self, args=None, kwargs=None, exc=None, throw=True, **options):
        """
        Custom retry with exponential backoff and jitter.
        """
        # Calculate backoff with jitter
        retry_count = self.request.retries
        
        # Exponential backoff: 2^retry * base_delay
        base_delay = options.get('countdown', 60)
        max_delay = options.get('max_retry_delay', 3600)
        
        backoff = min(base_delay * (2 ** retry_count), max_delay)
        
        # Add jitter (±25%)
        jitter_range = backoff * 0.25
        countdown = backoff + random.uniform(-jitter_range, jitter_range)
        
        logger.warning(
            f"Retrying task {self.name} (attempt {retry_count + 1}) "
            f"in {countdown:.1f} seconds. Error: {exc}"
        )
        
        options['countdown'] = countdown
        
        return super().retry(args=args, kwargs=kwargs, exc=exc, throw=throw, **options)
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """
        Handle task failure after all retries exhausted.
        """
        logger.error(
            f"Task {self.name}[{task_id}] failed permanently after "
            f"{self.request.retries} retries. Error: {exc}\n"
            f"Args: {args}\n"
            f"Kwargs: {kwargs}\n"
            f"Traceback: {einfo}"
        )
        
        # Send alert
        self.send_failure_alert(task_id, exc, args, kwargs)
    
    def send_failure_alert(self, task_id, exc, args, kwargs):
        """Send alert on permanent failure"""
        # Send to monitoring system (Sentry, email, Slack, etc.)
        try:
            from core.alerts import send_task_failure_alert
            send_task_failure_alert(
                task_name=self.name,
                task_id=task_id,
                error=str(exc),
                args=args,
                kwargs=kwargs
            )
        except Exception as e:
            logger.error(f"Failed to send alert: {e}")


@celery_app.task(
    bind=True,
    base=SmartRetryTask,
    name="celery_app.tasks.retry_strategies.process_with_retry"
)
def process_with_retry(self, data: dict):
    """
    Example task with smart retry logic.
    """
    try:
        # Simulate processing
        result = process_data(data)
        return result
    
    except TemporaryError as exc:
        # Temporary error - retry with backoff
        raise self.retry(exc=exc, countdown=60, max_retries=5)
    
    except PermanentError as exc:
        # Permanent error - don't retry
        logger.error(f"Permanent error, not retrying: {exc}")
        raise Reject(exc, requeue=False)
    
    except Exception as exc:
        # Unknown error - retry with exponential backoff
        raise self.retry(exc=exc)


@celery_app.task(
    bind=True,
    name="celery_app.tasks.retry_strategies.conditional_retry",
    autoretry_for=(ConnectionError, TimeoutError),
    retry_kwargs={'max_retries': 3},
    retry_backoff=True
)
def conditional_retry(self, api_url: str):
    """
    Task with conditional retry based on exception type.
    
    Only retries on specific exceptions.
    """
    import httpx
    
    try:
        response = httpx.get(api_url, timeout=30)
        response.raise_for_status()
        
        return response.json()
    
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code >= 500:
            # Server error - retry
            raise self.retry(exc=exc, countdown=120)
        elif exc.response.status_code == 429:
            # Rate limited - retry with longer delay
            retry_after = int(exc.response.headers.get('Retry-After', 300))
            raise self.retry(exc=exc, countdown=retry_after)
        else:
            # Client error - don't retry
            logger.error(f"Client error {exc.response.status_code}, not retrying")
            raise Reject(exc, requeue=False)
    
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        # Network error - retry automatically (autoretry_for)
        raise


@celery_app.task(
    bind=True,
    name="celery_app.tasks.retry_strategies.circuit_breaker_task"
)
def circuit_breaker_task(self, service_url: str):
    """
    Task with circuit breaker pattern.
    
    Stops retrying if service is consistently failing.
    """
    from core.redis_client import redis_client
    
    circuit_key = f"circuit_breaker:{service_url}"
    
    # Check circuit breaker state
    failures = redis_client.get(circuit_key, default=0)
    
    if int(failures) >= 5:
        # Circuit is open - don't even try
        logger.warning(f"Circuit breaker open for {service_url}")
        raise Reject("Circuit breaker open", requeue=True)
    
    try:
        # Make request
        response = make_request(service_url)
        
        # Success - reset circuit breaker
        redis_client.delete(circuit_key)
        
        return response
    
    except Exception as exc:
        # Increment failure counter
        redis_client.incr(circuit_key)
        redis_client.expire(circuit_key, 300)  # 5 minutes
        
        # Retry
        raise self.retry(exc=exc)
2. Error Classification & Handling
python# backend/celery_app/exceptions.py

class TaskError(Exception):
    """Base exception for task errors"""
    pass


class TemporaryError(TaskError):
    """Temporary error that should be retried"""
    pass


class PermanentError(TaskError):
    """Permanent error that should not be retried"""
    pass


class RetryableError(TaskError):
    """Error that can be retried with custom logic"""
    
    def __init__(self, message: str, retry_after: int = 60):
        super().__init__(message)
        self.retry_after = retry_after


# backend/celery_app/tasks/error_handling.py

from celery_app.celery import celery_app
from celery import Task
from celery.exceptions import Reject
import logging

from celery_app.exceptions import (
    TemporaryError,
    PermanentError,
    RetryableError
)


logger = logging.getLogger(__name__)


class ErrorHandlingTask(Task):
    """
    Task with comprehensive error handling.
    """
    
    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """
        Called when task is retried.
        """
        logger.warning(
            f"Task {self.name}[{task_id}] retry {self.request.retries + 1}. "
            f"Reason: {exc}"
        )
        
        # Update task metadata
        self.update_state(
            state='RETRY',
            meta={
                'exc_type': type(exc).__name__,
                'exc_message': str(exc),
                'retry_count': self.request.retries + 1
            }
        )
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """
        Called when task fails permanently.
        """
        logger.error(
            f"Task {self.name}[{task_id}] failed permanently. "
            f"Error: {exc}"
        )
        
        # Log to database
        from models.tasks import TaskFailure
        from database import SessionLocal
        
        db = SessionLocal()
        try:
            failure = TaskFailure(
                task_id=task_id,
                task_name=self.name,
                error_type=type(exc).__name__,
                error_message=str(exc),
                traceback=str(einfo),
                args=str(args),
                kwargs=str(kwargs)
            )
            db.add(failure)
            db.commit()
        finally:
            db.close()
        
        # Send notification
        self.send_failure_notification(task_id, exc)
    
    def send_failure_notification(self, task_id, exc):
        """Send failure notification"""
        from celery_app.tasks.email_tasks import send_email
        
        send_email.delay(
            to="admin@example.com",
            subject=f"Task Failure: {self.name}",
            body=f"Task {task_id} failed with error: {exc}",
            html=False
        )


@celery_app.task(
    bind=True,
    base=ErrorHandlingTask,
    name="celery_app.tasks.error_handling.safe_process"
)
def safe_process(self, data: dict):
    """
    Task with error classification and handling.
    """
    try:
        # Process data
        result = process_dangerous_operation(data)
        return result
    
    except ConnectionError as exc:
        # Network error - temporary, retry
        raise TemporaryError(f"Network error: {exc}")
    
    except ValueError as exc:
        # Invalid data - permanent, don't retry
        raise PermanentError(f"Invalid data: {exc}")
    
    except TimeoutError as exc:
        # Timeout - retry with longer delay
        raise RetryableError(f"Timeout: {exc}", retry_after=300)
    
    except Exception as exc:
        # Unknown error - log and decide
        logger.error(f"Unknown error in safe_process: {exc}")
        
        # Check if should retry
        if self.request.retries < 3:
            raise self.retry(exc=exc, countdown=120)
        else:
            # Too many retries - fail permanently
            raise PermanentError(f"Too many retries: {exc}")


@celery_app.task(
    bind=True,
    name="celery_app.tasks.error_handling.graceful_degradation"
)
def graceful_degradation(self, primary_service: str, fallback_service: str):
    """
    Task with graceful degradation to fallback service.
    """
    try:
        # Try primary service
        result = call_primary_service(primary_service)
        return {"source": "primary", "result": result}
    
    except Exception as exc:
        logger.warning(
            f"Primary service failed: {exc}. Trying fallback..."
        )
        
        try:
            # Try fallback service
            result = call_fallback_service(fallback_service)
            return {"source": "fallback", "result": result}
        
        except Exception as fallback_exc:
            logger.error(f"Fallback also failed: {fallback_exc}")
            
            # Both failed - retry or fail
            if self.request.retries < 2:
                raise self.retry(exc=fallback_exc, countdown=300)
            else:
                raise PermanentError(
                    f"Both primary and fallback failed: {exc}, {fallback_exc}"
                )
3. Dead Letter Queue (DLQ)
python# backend/celery_app/tasks/dlq.py

from celery_app.celery import celery_app
from celery import Task
from celery.exceptions import Reject
import logging
from datetime import datetime

from database import SessionLocal
from models.tasks import DeadLetterTask


logger = logging.getLogger(__name__)


class DLQTask(Task):
    """
    Task with Dead Letter Queue support.
    
    Failed tasks are moved to DLQ for manual inspection.
    """
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Move failed task to DLQ"""
        logger.error(f"Moving task {task_id} to DLQ")
        
        db = SessionLocal()
        try:
            dlq_task = DeadLetterTask(
                task_id=task_id,
                task_name=self.name,
                args=str(args),
                kwargs=str(kwargs),
                error_type=type(exc).__name__,
                error_message=str(exc),
                traceback=str(einfo),
                retry_count=self.request.retries,
                failed_at=datetime.utcnow()
            )
            db.add(dlq_task)
            db.commit()
        finally:
            db.close()


# Model for DLQ
# backend/models/tasks.py

from sqlalchemy import Column, String, Integer, DateTime, Text
from datetime import datetime

from database import Base


class DeadLetterTask(Base):
    """Dead Letter Queue for failed tasks"""
    __tablename__ = "dead_letter_tasks"
    
    id = Column(Integer, primary_key=True)
    task_id = Column(String, unique=True, nullable=False)
    task_name = Column(String, nullable=False)
    args = Column(Text)
    kwargs = Column(Text)
    error_type = Column(String)
    error_message = Column(Text)
    traceback = Column(Text)
    retry_count = Column(Integer, default=0)
    failed_at = Column(DateTime, default=datetime.utcnow)
    requeued_at = Column(DateTime, nullable=True)
    resolved = Column(Boolean, default=False)


# API endpoint to manage DLQ
# backend/api/v1/tasks.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.tasks import DeadLetterTask
from core.dependencies import get_current_admin_user


router = APIRouter()


@router.get("/dlq")
async def list_dead_letter_tasks(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """List tasks in Dead Letter Queue"""
    tasks = db.query(DeadLetterTask).filter(
        DeadLetterTask.resolved == False
    ).offset(skip).limit(limit).all()
    
    return {
        "total": db.query(DeadLetterTask).filter(
            DeadLetterTask.resolved == False
        ).count(),
        "items": tasks
    }


@router.post("/dlq/{task_id}/requeue")
async def requeue_dead_letter_task(
    task_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """Requeue a task from DLQ"""
    task = db.query(DeadLetterTask).filter(
        DeadLetterTask.task_id == task_id
    ).first()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Requeue task
    import json
    from celery_app.celery import celery_app
    
    args = json.loads(task.args) if task.args else []
    kwargs = json.loads(task.kwargs) if task.kwargs else {}
    
    result = celery_app.send_task(
        task.task_name,
        args=args,
        kwargs=kwargs
    )
    
    # Update DLQ record
    task.requeued_at = datetime.utcnow()
    task.resolved = True
    db.commit()
    
    return {
        "status": "requeued",
        "new_task_id": result.id
    }

🌸 TASK MONITORING WITH FLOWER
1. Flower Installation & Setup
bash# Install Flower
pip install flower

# Start Flower
celery -A celery_app.celery flower --port=5555

# With authentication
celery -A celery_app.celery flower \
    --port=5555 \
    --basic_auth=admin:secretpassword

# Access Flower UI
# http://localhost:5555
2. Flower Configuration
python# backend/celery_app/flower_config.py

from flower.utils import settings


class FlowerConfig:
    """Flower monitoring configuration"""
    
    # Server settings
    port = 5555
    address = "0.0.0.0"
    
    # Authentication
    basic_auth = ["admin:secretpassword"]
    
    # Broker API
    broker_api = "redis://localhost:6379/0"
    
    # Database (for persistent storage)
    db = "flower.db"
    persistent = True
    
    # Task settings
    max_tasks = 10000
    
    # Auto-refresh
    auto_refresh = True
    
    # URL prefix (if behind reverse proxy)
    url_prefix = ""
    
    # CORS
    cors_origins = ["http://localhost:3000"]
bash# Start Flower with config
celery -A celery_app.celery flower \
    --conf=celery_app.flower_config \
    --persistent=True \
    --db=flower.db
3. Custom Flower Dashboard
python# backend/celery_app/monitoring.py

from celery import current_app
from typing import Dict, Any, List
import logging


logger = logging.getLogger(__name__)


class CeleryMonitor:
    """
    Custom Celery monitoring utilities.
    
    Provides programmatic access to Celery stats.
    """
    
    def __init__(self):
        self.app = current_app
    
    def get_active_tasks(self) -> List[Dict[str, Any]]:
        """Get currently running tasks"""
        inspect = self.app.control.inspect()
        active = inspect.active()
        
        if not active:
            return []
        
        tasks = []
        for worker, task_list in active.items():
            for task in task_list:
                tasks.append({
                    "worker": worker,
                    "task_id": task["id"],
                    "task_name": task["name"],
                    "args": task["args"],
                    "kwargs": task["kwargs"],
                    "time_start": task.get("time_start")
                })
        
        return tasks
    
    def get_scheduled_tasks(self) -> List[Dict[str, Any]]:
        """Get scheduled (waiting) tasks"""
        inspect = self.app.control.inspect()
        scheduled = inspect.scheduled()
        
        if not scheduled:
            return []
        
        tasks = []
        for worker, task_list in scheduled.items():
            for task in task_list:
                tasks.append({
                    "worker": worker,
                    "task_id": task["request"]["id"],
                    "task_name": task["request"]["name"],
                    "eta": task["eta"]
                })
        
        return tasks
    
    def get_worker_stats(self) -> Dict[str, Any]:
        """Get worker statistics"""
        inspect = self.app.control.inspect()
        stats = inspect.stats()
        
        if not stats:
            return {}
        
        return stats
    
    def get_registered_tasks(self) -> List[str]:
        """Get list of registered tasks"""
        inspect = self.app.control.inspect()
        registered = inspect.registered()
        
        if not registered:
            return []
        
        # Flatten and deduplicate
        all_tasks = set()
        for worker, tasks in registered.items():
            all_tasks.update(tasks)
        
        return sorted(list(all_tasks))
    
    def get_queue_length(self, queue_name: str = "default") -> int:
        """Get number of tasks in queue"""
        from core.redis_client import redis_client
        
        # Queue key in Redis
        queue_key = f"celery:queue:{queue_name}"
        
        return redis_client.client.llen(queue_key)
    
    def get_task_info(self, task_id: str) -> Dict[str, Any]:
        """Get information about specific task"""
        from celery.result import AsyncResult
        
        result = AsyncResult(task_id, app=self.app)
        
        return {
            "task_id": task_id,
            "state": result.state,
            "result": result.result,
            "traceback": result.traceback,
            "info": result.info
        }
    
    def revoke_task(self, task_id: str, terminate: bool = False):
        """
        Revoke (cancel) a task.
        
        Args:
            task_id: Task ID to revoke
            terminate: If True, terminate the task if it's running
        """
        self.app.control.revoke(task_id, terminate=terminate)
        logger.info(f"Task {task_id} revoked (terminate={terminate})")
    
    def get_system_stats(self) -> Dict[str, Any]:
        """Get overall system statistics"""
        from core.redis_client import redis_client
        
        # Get queue lengths
        queues = ["default", "high_priority", "low_priority", "ocr", "email"]
        queue_stats = {
            queue: self.get_queue_length(queue)
            for queue in queues
        }
        
        # Get worker stats
        inspect = self.app.control.inspect()
        active = inspect.active() or {}
        scheduled = inspect.scheduled() or {}
        
        total_active = sum(len(tasks) for tasks in active.values())
        total_scheduled = sum(len(tasks) for tasks in scheduled.values())
        
        return {
            "workers": len(active.keys()),
            "active_tasks": total_active,
            "scheduled_tasks": total_scheduled,
            "queues": queue_stats,
            "total_queued": sum(queue_stats.values())
        }


# Global monitor instance
celery_monitor = CeleryMonitor()
4. Monitoring API Endpoints
python# backend/api/v1/monitoring.py

from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any

from celery_app.monitoring import celery_monitor
from core.dependencies import get_current_admin_user


router = APIRouter()


@router.get("/stats")
async def get_system_stats(
    admin: User = Depends(get_current_admin_user)
) -> Dict[str, Any]:
    """Get Celery system statistics"""
    return celery_monitor.get_system_stats()


@router.get("/tasks/active")
async def get_active_tasks(
    admin: User = Depends(get_current_admin_user)
):
    """Get currently running tasks"""
    return {
        "tasks": celery_monitor.get_active_tasks()
    }


@router.get("/tasks/scheduled")
async def get_scheduled_tasks(
    admin: User = Depends(get_current_admin_user)
):
    """Get scheduled tasks"""
    return {
        "tasks": celery_monitor.get_scheduled_tasks()
    }


@router.get("/tasks/{task_id}")
async def get_task_status(
    task_id: str,
    admin: User = Depends(get_current_admin_user)
):
    """Get task status and result"""
    return celery_monitor.get_task_info(task_id)


@router.post("/tasks/{task_id}/revoke")
async def revoke_task(
    task_id: str,
    terminate: bool = False,
    admin: User = Depends(get_current_admin_user)
):
    """Revoke (cancel) a task"""
    celery_monitor.revoke_task(task_id, terminate=terminate)
    
    return {
        "status": "revoked",
        "task_id": task_id,
        "terminated": terminate
    }


@router.get("/workers")
async def get_worker_stats(
    admin: User = Depends(get_current_admin_user)
):
    """Get worker statistics"""
    return celery_monitor.get_worker_stats()


@router.get("/queues")
async def get_queue_stats(
    admin: User = Depends(get_current_admin_user)
):
    """Get queue statistics"""
    queues = ["default", "high_priority", "low_priority", "ocr", "email"]
    
    return {
        queue: celery_monitor.get_queue_length(queue)
        for queue in queues
    }

⏰ PERIODIC TASKS (CELERY BEAT)
1. Celery Beat Configuration
python# backend/celery_app/beat_config.py

from celery.schedules import crontab, solar
from datetime import timedelta


# Beat schedule configuration
beat_schedule = {
    # ============================================
    # CLEANUP TASKS
    # ============================================
    
    # Delete old temporary files every day at 2 AM
    "cleanup-temp-files": {
        "task": "celery_app.tasks.cleanup_tasks.cleanup_temp_files",
        "schedule": crontab(hour=2, minute=0),
        "options": {"queue": "low_priority"}
    },
    
    # Delete old OCR results (>90 days) weekly
    "cleanup-old-ocr-results": {
        "task": "celery_app.tasks.cleanup_tasks.cleanup_old_ocr_results",
        "schedule": crontab(day_of_week=0, hour=3, minute=0),  # Sunday 3 AM
        "options": {"queue": "low_priority"}
    },
    
    # Vacuum database weekly
    "vacuum-database": {
        "task": "celery_app.tasks.cleanup_tasks.vacuum_database",
        "schedule": crontab(day_of_week=0, hour=4, minute=0),
        "options": {"queue": "low_priority"}
    },
    
    # ============================================
    # REPORTING TASKS
    # ============================================
    
    # Generate daily report at 8 AM
    "generate-daily-report": {
        "task": "celery_app.tasks.report_tasks.generate_daily_report",
        "schedule": crontab(hour=8, minute=0),
        "options": {"queue": "low_priority"}
    },
    
    # Generate weekly report on Monday 9 AM
    "generate-weekly-report": {
        "task": "celery_app.tasks.report_tasks.generate_weekly_report",
        "schedule": crontab(day_of_week=1, hour=9, minute=0),
        "options": {"queue": "low_priority"}
    },
    
    # Generate monthly report on 1st of month
    "generate-monthly-report": {
        "task": "celery_app.tasks.report_tasks.generate_monthly_report",
        "schedule": crontab(day_of_month=1, hour=10, minute=0),
        "options": {"queue": "low_priority"}
    },
    
    # ============================================
    # MONITORING & HEALTH CHECKS
    # ============================================
    
    # Health check every 5 minutes
    "health-check": {
        "task": "celery_app.tasks.monitoring_tasks.health_check",
        "schedule": timedelta(minutes=5),
    },
    
    # Check disk space every hour
    "check-disk-space": {
        "task": "celery_app.tasks.monitoring_tasks.check_disk_space",
        "schedule": crontab(minute=0),  # Every hour
    },
    
    # Monitor queue lengths every 10 minutes
    "monitor-queues": {
        "task": "celery_app.tasks.monitoring_tasks.monitor_queue_lengths",
        "schedule": timedelta(minutes=10),
    },
    
    # ============================================
    # DATA SYNC TASKS
    # ============================================
    
    # Sync with external API every 30 minutes
    "sync-external-data": {
        "task": "celery_app.tasks.sync_tasks.sync_external_api",
        "schedule": timedelta(minutes=30),
        "options": {"queue": "low_priority"}
    },
    
    # Backup database daily at 1 AM
    "backup-database": {
        "task": "celery_app.tasks.backup_tasks.backup_database",
        "schedule": crontab(hour=1, minute=0),
        "options": {"queue": "low_priority"}
    },
    
    # ============================================
    # USER ENGAGEMENT TASKS
    # ============================================
    
    # Send weekly digest emails on Friday 10 AM
    "send-weekly-digest": {
        "task": "celery_app.tasks.email_tasks.send_weekly_digest",
        "schedule": crontab(day_of_week=5, hour=10, minute=0),
        "options": {"queue": "email"}
    },
    
    # Send reminder emails for inactive users daily at 11 AM
    "send-inactive-user-reminders": {
        "task": "celery_app.tasks.email_tasks.send_inactive_reminders",
        "schedule": crontab(hour=11, minute=0),
        "options": {"queue": "email"}
    },
    
    # ============================================
    # SOLAR SCHEDULES (Sunrise/Sunset based)
    # ============================================
    
    # Run at sunrise
    "sunrise-task": {
        "task": "celery_app.tasks.scheduled_tasks.sunrise_task",
        "schedule": solar("sunrise", 40.7128, -74.0060),  # NYC coordinates
    },
}


# Update Celery config
from celery_app.config import CeleryConfig

CeleryConfig.beat_schedule = beat_schedule
2. Periodic Task Definitions
python# backend/celery_app/tasks/cleanup_tasks.py

from celery_app.celery import celery_app
from celery import Task
import logging
from datetime import datetime, timedelta
import os
import shutil

from database import SessionLocal
from models.documents import Document


logger = logging.getLogger(__name__)


@celery_app.task(name="celery_app.tasks.cleanup_tasks.cleanup_temp_files")
def cleanup_temp_files():
    """
    Clean up temporary files older than 24 hours.
    
    Runs daily via Celery Beat.
    """
    logger.info("Starting temporary files cleanup")
    
    temp_dir = "/tmp/ocr_temp"
    cutoff_time = datetime.now() - timedelta(hours=24)
    
    deleted_count = 0
    deleted_size = 0
    
    try:
        for filename in os.listdir(temp_dir):
            file_path = os.path.join(temp_dir, filename)
            
            # Check file modification time
            file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
            
            if file_mtime < cutoff_time:
                # Delete old file
                file_size = os.path.getsize(file_path)
                
                if os.path.isfile(file_path):
                    os.remove(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
                
                deleted_count += 1
                deleted_size += file_size
        
        logger.info(
            f"Cleanup complete: {deleted_count} files deleted, "
            f"{deleted_size / 1024 / 1024:.2f} MB freed"
        )
        
        return {
            "deleted_files": deleted_count,
            "freed_space_mb": deleted_size / 1024 / 1024
        }
    
    except Exception as exc:
        logger.error(f"Cleanup failed: {exc}")
        raise


@celery_app.task(name="celery_app.tasks.cleanup_tasks.cleanup_old_ocr_results")
def cleanup_old_ocr_results(days: int = 90):
    """
    Delete OCR results older than specified days.
    
    Args:
        days: Number of days to keep (default: 90)
    """
    logger.info(f"Cleaning up OCR results older than {days} days")
    
    db = SessionLocal()
    
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        # Find old documents
        old_documents = db.query(Document).filter(
            Document.created_at < cutoff_date,
            Document.status == "completed"
        ).all()
        
        deleted_count = 0
        
        for doc in old_documents:
            # Delete file
            if os.path.exists(doc.file_path):
                os.remove(doc.file_path)
            
            # Delete from database
            db.delete(doc)
            deleted_count += 1
        
        db.commit()
        
        logger.info(f"Deleted {deleted_count} old OCR results")
        
        return {"deleted_documents": deleted_count}
    
    except Exception as exc:
        logger.error(f"OCR cleanup failed: {exc}")
        db.rollback()
        raise
    
    finally:
        db.close()


@celery_app.task(name="celery_app.tasks.cleanup_tasks.vacuum_database")
def vacuum_database():
    """
    Vacuum PostgreSQL database to reclaim space.
    
    Runs weekly.
    """
    logger.info("Starting database vacuum")
    
    from sqlalchemy import create_engine, text
    from core.config import settings
    
    # Create engine with autocommit
    engine = create_engine(
        settings.DATABASE_URL,
        isolation_level="AUTOCOMMIT"
    )
    
    try:
        with engine.connect() as conn:
            # Vacuum analyze
            conn.execute(text("VACUUM ANALYZE"))
        
        logger.info("Database vacuum completed")
        
        return {"status": "completed"}
    
    except Exception as exc:
        logger.error(f"Database vacuum failed: {exc}")
        raise


@celery_app.task(name="celery_app.tasks.cleanup_tasks.health_check")
def health_check():
    """
    Periodic health check.
    
    Checks:
    - Database connectivity
    - Redis connectivity
    - Disk space
    """
    health_status = {
        "timestamp": datetime.utcnow().isoformat(),
        "status": "healthy",
        "checks": {}
    }
    
    # Check database
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        health_status["checks"]["database"] = "ok"
    except Exception as exc:
        health_status["checks"]["database"] = f"error: {exc}"
        health_status["status"] = "unhealthy"
    
    # Check Redis
    try:
        from core.redis_client import redis_client
        redis_client.ping()
        health_status["checks"]["redis"] = "ok"
    except Exception as exc:
        health_status["checks"]["redis"] = f"error: {exc}"
        health_status["status"] = "unhealthy"
    
    # Check disk space
    try:
        import shutil
        total, used, free = shutil.disk_usage("/")
        free_percent = (free / total) * 100
        
        if free_percent < 10:
            health_status["checks"]["disk_space"] = f"warning: {free_percent:.1f}% free"
            health_status["status"] = "degraded"
        else:
            health_status["checks"]["disk_space"] = f"ok: {free_percent:.1f}% free"
    except Exception as exc:
        health_status["checks"]["disk_space"] = f"error: {exc}"
    
    logger.info(f"Health check: {health_status['status']}")
    
    # Alert if unhealthy
    if health_status["status"] == "unhealthy":
        from celery_app.tasks.email_tasks import send_email
        send_email.delay(
            to="admin@example.com",
            subject="System Health Check Failed",
            body=f"Health check failed: {health_status}",
            html=False
        )
    
    return health_status
3. Starting Celery Beat
bash# Start Celery Beat scheduler
celery -A celery_app.celery beat --loglevel=info

# Start with custom schedule file
celery -A celery_app.celery beat \
    --loglevel=info \
    --schedule=/var/run/celerybeat-schedule

# Start Beat with Worker in same process (development only)
celery -A celery_app.celery worker --beat --loglevel=info

# Production: Run Beat and Worker separately
# Terminal 1: Beat
celery -A celery_app.celery beat --loglevel=info

# Terminal 2: Worker
celery -A celery_app.celery worker --loglevel=info
4. Dynamic Periodic Tasks
python# backend/celery_app/tasks/dynamic_periodic.py

from celery_app.celery import celery_app
from celery.schedules import crontab
from datetime import datetime
import logging


logger = logging.getLogger(__name__)


class DynamicPeriodicTaskManager:
    """
    Manager for adding/removing periodic tasks dynamically.
    
    Allows runtime modification of periodic tasks without restart.
    """
    
    @staticmethod
    def add_periodic_task(
        name: str,
        task: str,
        schedule: dict,
        args: tuple = (),
        kwargs: dict = None
    ):
        """
        Add a periodic task dynamically.
        
        Args:
            name: Unique name for the task
            task: Task name (e.g., 'celery_app.tasks.cleanup_tasks.cleanup_temp_files')
            schedule: Schedule dict (e.g., {'crontab': {'hour': 2, 'minute': 0}})
            args: Task arguments
            kwargs: Task keyword arguments
        """
        from django_celery_beat.models import PeriodicTask, CrontabSchedule
        
        # Create schedule
        if 'crontab' in schedule:
            cron = schedule['crontab']
            schedule_obj, _ = CrontabSchedule.objects.get_or_create(**cron)
        
        # Create periodic task
        PeriodicTask.objects.create(
            name=name,
            task=task,
            crontab=schedule_obj,
            args=args,
            kwargs=kwargs or {}
        )
        
        logger.info(f"Added periodic task: {name}")
    
    @staticmethod
    def remove_periodic_task(name: str):
        """Remove a periodic task"""
        from django_celery_beat.models import PeriodicTask
        
        PeriodicTask.objects.filter(name=name).delete()
        logger.info(f"Removed periodic task: {name}")
    
    @staticmethod
    def update_periodic_task(name: str, **kwargs):
        """Update a periodic task"""
        from django_celery_beat.models import PeriodicTask
        
        task = PeriodicTask.objects.get(name=name)
        
        for key, value in kwargs.items():
            setattr(task, key, value)
        
        task.save()
        logger.info(f"Updated periodic task: {name}")


# Example usage
@celery_app.task(name="celery_app.tasks.dynamic_periodic.create_user_report_task")
def create_user_report_task(user_id: str):
    """
    Create a periodic task for user report generation.
    
    Called when user subscribes to daily reports.
    """
    task_name = f"user_daily_report_{user_id}"
    
    DynamicPeriodicTaskManager.add_periodic_task(
        name=task_name,
        task="celery_app.tasks.report_tasks.generate_user_report",
        schedule={
            'crontab': {
                'hour': 8,
                'minute': 0
            }
        },
        kwargs={'user_id': user_id}
    )
    
    return {"status": "created", "task_name": task_name}

🎯 TASK PRIORITIES
1. Priority Queue Configuration
python# backend/celery_app/priority_config.py

from kombu import Exchange, Queue


# Priority levels
PRIORITY_HIGH = 10
PRIORITY_NORMAL = 5
PRIORITY_LOW = 1


# Queue definitions with priorities
priority_queues = (
    # Critical tasks (e.g., payment processing)
    Queue(
        "critical",
        Exchange("critical"),
        routing_key="critical",
        priority=PRIORITY_HIGH,
        queue_arguments={'x-max-priority': 10}
    ),
    
    # High priority (e.g., user-facing tasks)
    Queue(
        "high_priority",
        Exchange("high_priority"),
        routing_key="high_priority",
        priority=PRIORITY_HIGH,
        queue_arguments={'x-max-priority': 10}
    ),
    
    # Normal priority
    Queue(
        "default",
        Exchange("default"),
        routing_key="default",
        priority=PRIORITY_NORMAL,
        queue_arguments={'x-max-priority': 10}
    ),
    
    # Low priority (e.g., analytics, cleanup)
    Queue(
        "low_priority",
        Exchange("low_priority"),
        routing_key="low_priority",
        priority=PRIORITY_LOW,
        queue_arguments={'x-max-priority': 10}
    ),
)
2. Priority Task Examples
python# backend/celery_app/tasks/priority_tasks.py

from celery_app.celery import celery_app
import logging


logger = logging.getLogger(__name__)


@celery_app.task(
    name="celery_app.tasks.priority_tasks.critical_payment_processing",
    queue="critical",
    priority=10
)
def critical_payment_processing(payment_id: str):
    """
    Critical task - payment processing.
    
    Highest priority, processed first.
    """
    logger.info(f"Processing critical payment: {payment_id}")
    
    # Payment processing logic
    # ...
    
    return {"status": "completed", "payment_id": payment_id}


@celery_app.task(
    name="celery_app.tasks.priority_tasks.user_notification",
    queue="high_priority",
    priority=8
)
def user_notification(user_id: str, message: str):
    """
    High priority - user notification.
    
    Time-sensitive, should be processed quickly.
    """
    logger.info(f"Sending notification to user {user_id}")
    
    # Send notification
    # ...
    
    return {"status": "sent"}


@celery_app.task(
    name="celery_app.tasks.priority_tasks.analytics_processing",
    queue="low_priority",
    priority=1
)
def analytics_processing(data: dict):
    """
    Low priority - analytics.
    
    Can be delayed, processed when resources available.
    """
    logger.info("Processing analytics data")
    
    # Analytics processing
    # ...
    
    return {"status": "processed"}


# Dynamic priority based on context
@celery_app.task(
    name="celery_app.tasks.priority_tasks.adaptive_priority_task",
    bind=True
)
def adaptive_priority_task(self, task_type: str, data: dict):
    """
    Task with adaptive priority based on context.
    """
    # Determine priority
    if data.get("urgent"):
        priority = 10
        queue = "critical"
    elif data.get("user_facing"):
        priority = 7
        queue = "high_priority"
    else:
        priority = 3
        queue = "low_priority"
    
    # Re-route with appropriate priority
    self.apply_async(
        args=[task_type, data],
        queue=queue,
        priority=priority
    )
3. Priority Management API
python# backend/api/v1/tasks.py

from fastapi import APIRouter, Depends
from typing import Optional

from celery_app.celery import celery_app


router = APIRouter()


@router.post("/tasks/execute")
async def execute_task_with_priority(
    task_name: str,
    priority: Optional[int] = 5,
    queue: Optional[str] = "default",
    args: list = [],
    kwargs: dict = {}
):
    """
    Execute a task with specific priority.
    
    Priority levels:
    - 10: Critical
    - 7-9: High
    - 4-6: Normal
    - 1-3: Low
    """
    result = celery_app.send_task(
        task_name,
        args=args,
        kwargs=kwargs,
        queue=queue,
        priority=priority
    )
    
    return {
        "task_id": result.id,
        "task_name": task_name,
        "priority": priority,
        "queue": queue
    }




🔄 BACKGROUND TASKS & QUEUE MANAGEMENT - TEIL 3
Distributed Processing, Best Practices & Production

🌐 DISTRIBUTED TASK PROCESSING
1. Multi-Worker Setup
yaml# docker-compose.yml

version: '3.8'

services:
  # ============================================
  # BROKER & BACKEND
  # ============================================
  
  redis:
    image: redis:7-alpine
    container_name: ocr_redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes
    networks:
      - celery_network
  
  # ============================================
  # CELERY WORKERS
  # ============================================
  
  # General purpose worker
  celery_worker_default:
    build: .
    command: celery -A celery_app.celery worker -Q default,high_priority -c 4 --loglevel=info -n worker_default@%h
    volumes:
      - ./backend:/app
      - shared_storage:/app/uploads
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/0
      - CELERY_RESULT_BACKEND=redis://redis:6379/1
    depends_on:
      - redis
      - postgres
    networks:
      - celery_network
    deploy:
      replicas: 2  # 2 instances
      resources:
        limits:
          cpus: '2'
          memory: 2G
  
  # OCR processing worker (CPU intensive)
  celery_worker_ocr:
    build: .
    command: celery -A celery_app.celery worker -Q ocr -c 2 --loglevel=info -n worker_ocr@%h
    volumes:
      - ./backend:/app
      - shared_storage:/app/uploads
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/0
      - CELERY_RESULT_BACKEND=redis://redis:6379/1
    depends_on:
      - redis
      - postgres
    networks:
      - celery_network
    deploy:
      replicas: 3  # 3 OCR workers
      resources:
        limits:
          cpus: '4'
          memory: 4G
  
  # Email worker (I/O bound)
  celery_worker_email:
    build: .
    command: celery -A celery_app.celery worker -Q email -c 10 --loglevel=info -n worker_email@%h
    volumes:
      - ./backend:/app
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/0
      - CELERY_RESULT_BACKEND=redis://redis:6379/1
    depends_on:
      - redis
    networks:
      - celery_network
    deploy:
      replicas: 2
      resources:
        limits:
          cpus: '1'
          memory: 1G
  
  # Low priority worker
  celery_worker_low:
    build: .
    command: celery -A celery_app.celery worker -Q low_priority -c 2 --loglevel=info -n worker_low@%h
    volumes:
      - ./backend:/app
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/0
      - CELERY_RESULT_BACKEND=redis://redis:6379/1
    depends_on:
      - redis
      - postgres
    networks:
      - celery_network
    deploy:
      replicas: 1
      resources:
        limits:
          cpus: '1'
          memory: 1G
  
  # ============================================
  # CELERY BEAT (Scheduler)
  # ============================================
  
  celery_beat:
    build: .
    command: celery -A celery_app.celery beat --loglevel=info
    volumes:
      - ./backend:/app
      - celerybeat_data:/var/run
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/0
      - CELERY_RESULT_BACKEND=redis://redis:6379/1
    depends_on:
      - redis
      - postgres
    networks:
      - celery_network
  
  # ============================================
  # FLOWER (Monitoring)
  # ============================================
  
  flower:
    build: .
    command: celery -A celery_app.celery flower --port=5555 --broker=redis://redis:6379/0
    ports:
      - "5555:5555"
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/0
      - CELERY_RESULT_BACKEND=redis://redis:6379/1
    depends_on:
      - redis
      - celery_worker_default
    networks:
      - celery_network

volumes:
  redis_data:
  celerybeat_data:
  shared_storage:

networks:
  celery_network:
    driver: bridge
2. Worker Pool Strategies
python# backend/celery_app/worker_config.py

"""
Celery Worker Pool Types and Configuration.

Pool Types:
1. prefork (default) - Multiprocessing, CPU-bound tasks
2. eventlet - Green threads, I/O-bound tasks
3. gevent - Green threads, I/O-bound tasks
4. solo - Single process, debugging
5. threads - Threading, I/O-bound tasks
"""


# Prefork Pool (CPU-intensive tasks)
PREFORK_WORKER_CONFIG = {
    "pool": "prefork",
    "concurrency": 4,  # Number of processes
    "max_tasks_per_child": 1000,  # Restart worker after N tasks
    "worker_prefetch_multiplier": 4,  # Tasks to prefetch
}


# Eventlet Pool (I/O-intensive tasks)
EVENTLET_WORKER_CONFIG = {
    "pool": "eventlet",
    "concurrency": 100,  # Number of green threads
}


# Gevent Pool (I/O-intensive tasks)
GEVENT_WORKER_CONFIG = {
    "pool": "gevent",
    "concurrency": 100,  # Number of green threads
}


# Configuration per queue
WORKER_CONFIGURATIONS = {
    "ocr": PREFORK_WORKER_CONFIG,
    "email": EVENTLET_WORKER_CONFIG,
    "default": PREFORK_WORKER_CONFIG,
    "low_priority": PREFORK_WORKER_CONFIG,
}
bash# Start workers with different pools

# Prefork pool (default) - for CPU-bound tasks
celery -A celery_app.celery worker \
    -Q ocr \
    -c 4 \
    --pool=prefork \
    -n worker_ocr@%h

# Eventlet pool - for I/O-bound tasks (emails, API calls)
pip install eventlet
celery -A celery_app.celery worker \
    -Q email \
    -c 100 \
    --pool=eventlet \
    -n worker_email@%h

# Gevent pool - alternative for I/O-bound tasks
pip install gevent
celery -A celery_app.celery worker \
    -Q api_calls \
    -c 100 \
    --pool=gevent \
    -n worker_api@%h

# Solo pool - for debugging (single process, no concurrency)
celery -A celery_app.celery worker \
    --pool=solo \
    -n worker_debug@%h
3. Task Routing & Distribution
python# backend/celery_app/routing.py

from typing import Dict, Any
import logging


logger = logging.getLogger(__name__)


class TaskRouter:
    """
    Custom task router for intelligent task distribution.
    
    Routes tasks based on:
    - Task type
    - Priority
    - Resource requirements
    - Geographic location
    """
    
    def route_for_task(self, task: str, args: tuple = None, kwargs: Dict = None) -> Dict[str, Any]:
        """
        Route task to appropriate queue and worker.
        
        Args:
            task: Task name
            args: Task arguments
            kwargs: Task keyword arguments
        
        Returns:
            Routing configuration
        """
        # OCR tasks
        if "ocr" in task.lower():
            return self._route_ocr_task(task, args, kwargs)
        
        # Email tasks
        elif "email" in task.lower():
            return self._route_email_task(task, args, kwargs)
        
        # Report tasks
        elif "report" in task.lower():
            return self._route_report_task(task, args, kwargs)
        
        # Cleanup tasks
        elif "cleanup" in task.lower():
            return {
                "queue": "low_priority",
                "priority": 1
            }
        
        # Default routing
        else:
            return {
                "queue": "default",
                "priority": 5
            }
    
    def _route_ocr_task(self, task: str, args: tuple, kwargs: Dict) -> Dict[str, Any]:
        """Route OCR tasks based on document size and priority"""
        # Check if urgent
        is_urgent = kwargs.get("urgent", False) if kwargs else False
        
        if is_urgent:
            return {
                "queue": "high_priority",
                "priority": 9
            }
        else:
            return {
                "queue": "ocr",
                "priority": 7
            }
    
    def _route_email_task(self, task: str, args: tuple, kwargs: Dict) -> Dict[str, Any]:
        """Route email tasks"""
        # Check if transactional (password reset, verification)
        is_transactional = kwargs.get("transactional", False) if kwargs else False
        
        if is_transactional:
            return {
                "queue": "high_priority",
                "priority": 8
            }
        else:
            return {
                "queue": "email",
                "priority": 6
            }
    
    def _route_report_task(self, task: str, args: tuple, kwargs: Dict) -> Dict[str, Any]:
        """Route report generation tasks"""
        return {
            "queue": "low_priority",
            "priority": 2
        }


# Apply router to Celery config
from celery_app.celery import celery_app

task_router = TaskRouter()
celery_app.conf.task_routes = (task_router.route_for_task,)
4. Geographic Distribution
python# backend/celery_app/geo_routing.py

from typing import Dict, Any
import logging


logger = logging.getLogger(__name__)


class GeoRouter:
    """
    Geographic task routing.
    
    Routes tasks to workers in specific regions for:
    - Reduced latency
    - Data locality
    - Compliance (GDPR, data residency)
    """
    
    # Region to broker mapping
    REGION_BROKERS = {
        "us-east": "redis://us-east-redis:6379/0",
        "us-west": "redis://us-west-redis:6379/0",
        "eu-west": "redis://eu-west-redis:6379/0",
        "asia": "redis://asia-redis:6379/0",
    }
    
    @classmethod
    def route_by_region(cls, task: str, region: str, **options) -> str:
        """
        Route task to specific region.
        
        Args:
            task: Task name
            region: Target region
            **options: Additional task options
        
        Returns:
            Task ID
        """
        from celery import Celery
        
        # Get broker for region
        broker_url = cls.REGION_BROKERS.get(region)
        
        if not broker_url:
            logger.warning(f"Unknown region {region}, using default")
            broker_url = cls.REGION_BROKERS["us-east"]
        
        # Create Celery app for region
        regional_app = Celery(broker=broker_url)
        
        # Send task to regional broker
        result = regional_app.send_task(task, **options)
        
        logger.info(f"Task {task} routed to region {region}")
        
        return result.id


# Usage example
@celery_app.task(name="celery_app.tasks.geo_tasks.process_eu_data")
def process_eu_data(data: dict):
    """
    Process EU data in EU region (GDPR compliance).
    """
    # This task will only run on EU workers
    logger.info("Processing data in EU region")
    
    # Processing logic
    # ...
    
    return {"status": "processed", "region": "eu-west"}


# API endpoint for regional task execution
from fastapi import APIRouter

router = APIRouter()


@router.post("/tasks/execute-regional")
async def execute_regional_task(
    task_name: str,
    region: str,
    args: list = [],
    kwargs: dict = {}
):
    """Execute task in specific region"""
    task_id = GeoRouter.route_by_region(
        task_name,
        region=region,
        args=args,
        kwargs=kwargs
    )
    
    return {
        "task_id": task_id,
        "region": region
    }

🎼 ADVANCED WORKFLOWS
1. Canvas Primitives
python# backend/celery_app/workflows/canvas.py

from celery import chain, group, chord, signature
from celery_app.celery import celery_app
import logging


logger = logging.getLogger(__name__)


# ============================================
# 1. CHAIN - Sequential execution
# ============================================

@celery_app.task(name="celery_app.workflows.canvas.step1")
def step1(data):
    """First step in chain"""
    logger.info(f"Step 1: {data}")
    return data + 1


@celery_app.task(name="celery_app.workflows.canvas.step2")
def step2(data):
    """Second step in chain"""
    logger.info(f"Step 2: {data}")
    return data * 2


@celery_app.task(name="celery_app.workflows.canvas.step3")
def step3(data):
    """Third step in chain"""
    logger.info(f"Step 3: {data}")
    return data - 5


def create_chain_workflow(initial_value: int):
    """
    Create a chain workflow.
    
    Flow: step1 -> step2 -> step3
    """
    workflow = chain(
        step1.s(initial_value),
        step2.s(),
        step3.s()
    )
    
    result = workflow.apply_async()
    
    return result


# ============================================
# 2. GROUP - Parallel execution
# ============================================

@celery_app.task(name="celery_app.workflows.canvas.parallel_task")
def parallel_task(n):
    """Task to run in parallel"""
    logger.info(f"Processing {n}")
    return n ** 2


def create_group_workflow(numbers: list):
    """
    Create a group workflow.
    
    All tasks run in parallel.
    """
    job = group(
        parallel_task.s(n) for n in numbers
    )
    
    result = job.apply_async()
    
    return result


# ============================================
# 3. CHORD - Parallel + Callback
# ============================================

@celery_app.task(name="celery_app.workflows.canvas.process_item")
def process_item(item):
    """Process single item"""
    logger.info(f"Processing item: {item}")
    return item * 2


@celery_app.task(name="celery_app.workflows.canvas.aggregate_results")
def aggregate_results(results):
    """Aggregate results from parallel tasks"""
    logger.info(f"Aggregating {len(results)} results")
    return sum(results)


def create_chord_workflow(items: list):
    """
    Create a chord workflow.
    
    Flow: Parallel processing -> Single aggregation
    """
    callback = aggregate_results.s()
    
    workflow = chord(
        (process_item.s(item) for item in items),
        callback
    )
    
    result = workflow.apply_async()
    
    return result


# ============================================
# 4. COMPLEX WORKFLOW - Combining primitives
# ============================================

@celery_app.task(name="celery_app.workflows.canvas.validate_data")
def validate_data(data):
    """Validate input data"""
    logger.info("Validating data")
    # Validation logic
    return data


@celery_app.task(name="celery_app.workflows.canvas.process_chunk")
def process_chunk(chunk):
    """Process data chunk"""
    logger.info(f"Processing chunk of {len(chunk)} items")
    return [item * 2 for item in chunk]


@celery_app.task(name="celery_app.workflows.canvas.merge_results")
def merge_results(chunks):
    """Merge processed chunks"""
    logger.info("Merging results")
    merged = []
    for chunk in chunks:
        merged.extend(chunk)
    return merged


@celery_app.task(name="celery_app.workflows.canvas.save_to_database")
def save_to_database(data):
    """Save final results"""
    logger.info(f"Saving {len(data)} items to database")
    # Save logic
    return {"saved": len(data)}


def create_complex_workflow(data: list, chunk_size: int = 100):
    """
    Create complex workflow combining all primitives.
    
    Flow:
    1. Validate data
    2. Split into chunks and process in parallel
    3. Merge results
    4. Save to database
    """
    # Split data into chunks
    chunks = [data[i:i + chunk_size] for i in range(0, len(data), chunk_size)]
    
    # Create workflow
    workflow = chain(
        validate_data.s(data),
        chord(
            (process_chunk.s(chunk) for chunk in chunks),
            merge_results.s()
        ),
        save_to_database.s()
    )
    
    result = workflow.apply_async()
    
    return result


# ============================================
# 5. MAP - Apply function to iterable
# ============================================

@celery_app.task(name="celery_app.workflows.canvas.transform_item")
def transform_item(item):
    """Transform single item"""
    return item.upper()


def create_map_workflow(items: list):
    """
    Create a map workflow.
    
    Applies transform_item to each item in parallel.
    """
    job = group(transform_item.s(item) for item in items)
    
    result = job.apply_async()
    
    return result


# ============================================
# 6. STARMAP - Map with multiple arguments
# ============================================

@celery_app.task(name="celery_app.workflows.canvas.add_numbers")
def add_numbers(a, b):
    """Add two numbers"""
    return a + b


def create_starmap_workflow(number_pairs: list):
    """
    Create a starmap workflow.
    
    Example: [(1, 2), (3, 4), (5, 6)]
    """
    job = group(
        add_numbers.s(a, b) for a, b in number_pairs
    )
    
    result = job.apply_async()
    
    return result
2. Real-World Workflow Examples
python# backend/celery_app/workflows/real_world.py

from celery import chain, group, chord
from celery_app.celery import celery_app
import logging


logger = logging.getLogger(__name__)


# ============================================
# WORKFLOW 1: Batch OCR Processing
# ============================================

@celery_app.task(name="celery_app.workflows.real_world.prepare_documents")
def prepare_documents(document_ids: list):
    """Prepare documents for processing"""
    logger.info(f"Preparing {len(document_ids)} documents")
    
    # Fetch documents from database
    from database import SessionLocal
    from models.documents import Document
    
    db = SessionLocal()
    try:
        documents = db.query(Document).filter(
            Document.id.in_(document_ids)
        ).all()
        
        return [
            {"id": str(doc.id), "path": doc.file_path}
            for doc in documents
        ]
    finally:
        db.close()


@celery_app.task(name="celery_app.workflows.real_world.process_single_ocr")
def process_single_ocr(document_data: dict):
    """Process single document with OCR"""
    logger.info(f"Processing OCR for document {document_data['id']}")
    
    # OCR processing
    from core.ocr import OCRProcessor
    
    processor = OCRProcessor()
    result = processor.process_document(document_data["path"])
    
    return {
        "document_id": document_data["id"],
        "result": result
    }


@celery_app.task(name="celery_app.workflows.real_world.save_ocr_results")
def save_ocr_results(results: list):
    """Save OCR results to database"""
    logger.info(f"Saving {len(results)} OCR results")
    
    from database import SessionLocal
    from models.documents import Document
    
    db = SessionLocal()
    try:
        for result in results:
            doc = db.query(Document).filter(
                Document.id == result["document_id"]
            ).first()
            
            if doc:
                doc.ocr_result = result["result"]
                doc.status = "completed"
        
        db.commit()
        
        return {"saved": len(results)}
    finally:
        db.close()


def batch_ocr_workflow(document_ids: list):
    """
    Batch OCR processing workflow.
    
    Steps:
    1. Prepare documents
    2. Process each in parallel
    3. Save all results
    """
    workflow = chain(
        prepare_documents.s(document_ids),
        chord(
            (process_single_ocr.s(doc) for doc in []),  # Will be populated by prepare_documents
            save_ocr_results.s()
        )
    )
    
    # Alternative using immutable signature
    workflow = chain(
        prepare_documents.s(document_ids),
        lambda docs: chord(
            (process_single_ocr.s(doc) for doc in docs),
            save_ocr_results.s()
        ).apply_async()
    )
    
    result = workflow.apply_async()
    
    return result


# ============================================
# WORKFLOW 2: Report Generation Pipeline
# ============================================

@celery_app.task(name="celery_app.workflows.real_world.fetch_analytics_data")
def fetch_analytics_data(start_date: str, end_date: str):
    """Fetch analytics data from database"""
    logger.info(f"Fetching analytics data from {start_date} to {end_date}")
    
    # Fetch data
    # ...
    
    return {
        "users": 1000,
        "documents": 5000,
        "ocr_processed": 4500
    }


@celery_app.task(name="celery_app.workflows.real_world.generate_charts")
def generate_charts(data: dict):
    """Generate charts from data"""
    logger.info("Generating charts")
    
    # Chart generation
    # ...
    
    return {"chart_path": "/reports/charts.png"}


@celery_app.task(name="celery_app.workflows.real_world.generate_pdf_report")
def generate_pdf_report(data: dict, chart_info: dict):
    """Generate PDF report"""
    logger.info("Generating PDF report")
    
    # PDF generation
    # ...
    
    return {"pdf_path": "/reports/report.pdf"}


@celery_app.task(name="celery_app.workflows.real_world.email_report")
def email_report(report_info: dict):
    """Email report to recipients"""
    logger.info(f"Emailing report: {report_info['pdf_path']}")
    
    from celery_app.tasks.email_tasks import send_email
    
    send_email.delay(
        to="admin@example.com",
        subject="Weekly Report",
        body="Your weekly report is attached.",
        attachments=[{"path": report_info["pdf_path"]}]
    )
    
    return {"status": "sent"}


def report_generation_workflow(start_date: str, end_date: str):
    """
    Report generation workflow.
    
    Steps:
    1. Fetch analytics data
    2. Generate charts (parallel with data fetching if needed)
    3. Generate PDF report
    4. Email report
    """
    workflow = chain(
        fetch_analytics_data.s(start_date, end_date),
        generate_charts.s(),
        generate_pdf_report.s(),
        email_report.s()
    )
    
    result = workflow.apply_async()
    
    return result


# ============================================
# WORKFLOW 3: Data Import Pipeline
# ============================================

@celery_app.task(name="celery_app.workflows.real_world.download_file")
def download_file(url: str):
    """Download file from URL"""
    logger.info(f"Downloading file from {url}")
    
    import httpx
    
    response = httpx.get(url)
    
    # Save to temp file
    import tempfile
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as f:
        f.write(response.content)
        return {"file_path": f.name}


@celery_app.task(name="celery_app.workflows.real_world.parse_csv")
def parse_csv(file_info: dict):
    """Parse CSV file"""
    logger.info(f"Parsing CSV: {file_info['file_path']}")
    
    import csv
    
    records = []
    with open(file_info["file_path"], "r") as f:
        reader = csv.DictReader(f)
        records = list(reader)
    
    return records


@celery_app.task(name="celery_app.workflows.real_world.validate_record")
def validate_record(record: dict):
    """Validate single record"""
    # Validation logic
    # ...
    
    return record


@celery_app.task(name="celery_app.workflows.real_world.save_records")
def save_records(records: list):
    """Save validated records to database"""
    logger.info(f"Saving {len(records)} records")
    
    # Save to database
    # ...
    
    return {"saved": len(records)}


@celery_app.task(name="celery_app.workflows.real_world.cleanup_temp_file")
def cleanup_temp_file(result: dict):
    """Clean up temporary files"""
    logger.info("Cleaning up temporary files")
    
    import os
    
    # Cleanup logic
    # ...
    
    return result


def data_import_workflow(url: str):
    """
    Data import workflow.
    
    Steps:
    1. Download file
    2. Parse CSV
    3. Validate each record in parallel
    4. Save all records
    5. Cleanup
    """
    workflow = chain(
        download_file.s(url),
        parse_csv.s(),
        chord(
            # Will be populated by parse_csv
            group([]),
            save_records.s()
        ),
        cleanup_temp_file.s()
    )
    
    result = workflow.apply_async()
    
    return result

✅ BEST PRACTICES
1. Task Design Principles
python# backend/celery_app/best_practices/task_design.py

"""
CELERY TASK BEST PRACTICES

1. IDEMPOTENT TASKS
   - Tasks should produce same result when executed multiple times
   - Handle retries gracefully
"""

from celery_app.celery import celery_app
import logging


logger = logging.getLogger(__name__)


# ✅ GOOD: Idempotent task
@celery_app.task(name="celery_app.best_practices.process_order_idempotent")
def process_order_idempotent(order_id: str):
    """
    Idempotent order processing.
    
    Can be safely retried.
    """
    from database import SessionLocal
    from models.orders import Order
    
    db = SessionLocal()
    try:
        order = db.query(Order).filter(Order.id == order_id).first()
        
        # Check if already processed
        if order.status == "processed":
            logger.info(f"Order {order_id} already processed, skipping")
            return {"status": "already_processed"}
        
        # Process order
        order.status = "processing"
        db.commit()
        
        # ... processing logic ...
        
        order.status = "processed"
        db.commit()
        
        return {"status": "success"}
    
    finally:
        db.close()


# ❌ BAD: Non-idempotent task
@celery_app.task(name="celery_app.best_practices.increment_counter_bad")
def increment_counter_bad(counter_id: str):
    """
    Non-idempotent counter increment.
    
    Retry will double-increment!
    """
    from database import SessionLocal
    from models.counters import Counter
    
    db = SessionLocal()
    try:
        counter = db.query(Counter).filter(Counter.id == counter_id).first()
        
        # BAD: No check if already incremented
        counter.value += 1
        db.commit()
    
    finally:
        db.close()


"""
2. SMALL, FOCUSED TASKS
   - One task = one responsibility
   - Easier to test, debug, and maintain
"""


# ✅ GOOD: Small, focused tasks
@celery_app.task(name="celery_app.best_practices.send_welcome_email")
def send_welcome_email(user_email: str):
    """Send welcome email only"""
    # Just send email
    pass


@celery_app.task(name="celery_app.best_practices.create_user_profile")
def create_user_profile(user_id: str):
    """Create user profile only"""
    # Just create profile
    pass


# ❌ BAD: Monolithic task
@celery_app.task(name="celery_app.best_practices.onboard_user_monolithic")
def onboard_user_monolithic(user_data: dict):
    """
    Does too many things.
    
    Hard to maintain and debug.
    """
    # Create user
    # Send welcome email
    # Create profile
    # Send to CRM
    # Generate API key
    # ... (too many responsibilities)
    pass


"""
3. AVOID SHARED STATE
   - Tasks should not depend on shared mutable state
   - Use database or cache for coordination
"""


# ✅ GOOD: Stateless task
@celery_app.task(name="celery_app.best_practices.process_document_stateless")
def process_document_stateless(document_id: str):
    """
    Stateless document processing.
    
    All state from database.
    """
    from database import SessionLocal
    from models.documents import Document
    
    db = SessionLocal()
    try:
        # Fetch state from database
        doc = db.query(Document).filter(Document.id == document_id).first()
        
        # Process using doc data
        # ...
        
        # Save state back to database
        db.commit()
    
    finally:
        db.close()


# ❌ BAD: Stateful task
processing_state = {}  # Global state - BAD!


@celery_app.task(name="celery_app.best_practices.process_with_shared_state")
def process_with_shared_state(doc_id: str):
    """
    Uses global state.
    
    Will fail in distributed environment!
    """
    global processing_state
    
    # BAD: Using global variable
    processing_state[doc_id] = "processing"
    
    # ... processing ...
    
    processing_state[doc_id] = "done"


"""
4. EXPLICIT IS BETTER THAN IMPLICIT
   - Pass all necessary data explicitly
   - Don't rely on global configuration
"""


# ✅ GOOD: Explicit parameters
@celery_app.task(name="celery_app.best_practices.export_data_explicit")
def export_data_explicit(
    user_id: str,
    start_date: str,
    end_date: str,
    format: str,
    email: str
):
    """
    All parameters explicit.
    
    Easy to understand and test.
    """
    # Process with given parameters
    pass


# ❌ BAD: Implicit configuration
@celery_app.task(name="celery_app.best_practices.export_data_implicit")
def export_data_implicit(user_id: str):
    """
    Relies on global config.
    
    Hard to test with different configurations.
    """
    from core.config import settings
    
    # BAD: Implicit dependencies on global config
    format = settings.DEFAULT_EXPORT_FORMAT
    # ...


"""
5. PROPER ERROR HANDLING
   - Catch specific exceptions
   - Provide meaningful error messages
   - Log appropriately
"""


# ✅ GOOD: Specific error handling
@celery_app.task(
    bind=True,
    name="celery_app.best_practices.robust_task",
    autoretry_for=(ConnectionError, TimeoutError),
    max_retries=3
)
def robust_task(self, data: dict):
    """
    Proper error handling.
    
    Retries on specific errors.
    """
    try:
        # Main logic
        result = process_data(data)
        return result
    
    except ValueError as exc:
        # Permanent error - don't retry
        logger.error(f"Invalid data: {exc}")
        raise
    
    except ConnectionError as exc:
        # Temporary error - will retry (autoretry_for)
        logger.warning(f"Connection error, will retry: {exc}")
        raise
    
    except Exception as exc:
        # Unknown error - log and decide
        logger.error(f"Unexpected error: {exc}", exc_info=True)
        
        if self.request.retries < 2:
            raise self.retry(exc=exc, countdown=60)
        else:
            raise


# ❌ BAD: Catching all exceptions
@celery_app.task(name="celery_app.best_practices.catch_all_task")
def catch_all_task(data: dict):
    """
    Catches everything.
    
    Masks errors and makes debugging hard.
    """
    try:
        # Logic
        pass
    except Exception:
        # BAD: Silently catching everything
        pass  # What happened?!


"""
6. TIMEOUT CONFIGURATION
   - Set appropriate timeouts
   - Prevent tasks from hanging forever
"""


# ✅ GOOD: Explicit timeout
@celery_app.task(
    name="celery_app.best_practices.timed_task",
    time_limit=300,  # Hard limit: 5 minutes
    soft_time_limit=240  # Soft limit: 4 minutes
)
def timed_task(data: dict):
    """
    Task with timeout protection.
    
    Will be killed after 5 minutes.
    """
    from celery.exceptions import SoftTimeLimitExceeded
    
    try:
        # Long-running operation
        result = expensive_operation(data)
        return result
    
    except SoftTimeLimitExceeded:
        # Graceful cleanup before hard limit
        logger.warning("Task approaching time limit, cleaning up...")
        cleanup()
        raise


"""
7. LOGGING & MONITORING
   - Log important events
   - Include context in logs
   - Use structured logging
"""


# ✅ GOOD: Proper logging
@celery_app.task(
    bind=True,
    name="celery_app.best_practices.well_logged_task"
)
def well_logged_task(self, document_id: str, user_id: str):
    """
    Well-logged task.
    
    Includes context and uses different log levels.
    """
    logger.info(
        f"Starting document processing",
        extra={
            "task_id": self.request.id,
            "document_id": document_id,
            "user_id": user_id
        }
    )
    
    try:
        # Process
        result = process(document_id)
        
        logger.info(
            f"Document processing completed",
            extra={
                "task_id": self.request.id,
                "document_id": document_id,
                "result": result
            }
        )
        
        return result
    
    except Exception as exc:
        logger.error(
            f"Document processing failed",
            extra={
                "task_id": self.request.id,
                "document_id": document_id,
                "error": str(exc)
            },
            exc_info=True
        )
        raise
2. Performance Optimization
python# backend/celery_app/best_practices/performance.py

"""
PERFORMANCE OPTIMIZATION TIPS
"""

from celery_app.celery import celery_app
import logging


logger = logging.getLogger(__name__)


"""
1. BATCH PROCESSING
   - Process multiple items together
   - Reduce overhead
"""


# ✅ GOOD: Batch processing
@celery_app.task(name="celery_app.best_practices.batch_insert")
def batch_insert(records: list):
    """
    Insert multiple records in one transaction.
    
    Much faster than individual inserts.
    """
    from database import SessionLocal
    from models.data import DataRecord
    
    db = SessionLocal()
    try:
        # Bulk insert
        db.bulk_insert_mappings(DataRecord, records)
        db.commit()
        
        logger.info(f"Inserted {len(records)} records in batch")
    
    finally:
        db.close()


# ❌ BAD: Individual processing
@celery_app.task(name="celery_app.best_practices.single_insert")
def single_insert(record: dict):
    """
    Processes one record at a time.
    
    Inefficient for large volumes.
    """
    from database import SessionLocal
    from models.data import DataRecord
    
    db = SessionLocal()
    try:
        db.add(DataRecord(**record))
        db.commit()
    finally:
        db.close()


"""
2. CHUNKING
   - Split large datasets into manageable chunks
   - Process chunks in parallel
"""


@celery_app.task(name="celery_app.best_practices.process_chunk")
def process_chunk(chunk: list):
    """Process a chunk of data"""
    # Process chunk
    return len(chunk)


def process_large_dataset(data: list, chunk_size: int = 1000):
    """
    Process large dataset in chunks.
    
    Prevents memory issues and enables parallelism.
    """
    from celery import group
    
    # Split into chunks
    chunks = [
        data[i:i + chunk_size]
        for i in range(0, len(data), chunk_size)
    ]
    
    # Process chunks in parallel
    job = group(
        process_chunk.s(chunk) for chunk in chunks
    )
    
    return job.apply_async()


"""
3. CACHING
   - Cache expensive computations
   - Avoid redundant work
"""


@celery_app.task(name="celery_app.best_practices.cached_task")
def cached_task(key: str):
    """
    Task with result caching.
    
    Checks cache before computing.
    """
    from core.redis_client import redis_client
    
    # Check cache
    cached_result = redis_client.get(f"task_result:{key}")
    if cached_result:
        logger.info(f"Cache hit for {key}")
        return cached_result
    
    # Compute
    result = expensive_computation(key)
    
    # Cache result
    redis_client.set(f"task_result:{key}", result, expire=3600)
    
    return result


"""
4. DATABASE CONNECTION POOLING
   - Reuse database connections
   - Configure pool size appropriately
"""

# Configuration
SQLALCHEMY_POOL_SIZE = 10
SQLALCHEMY_MAX_OVERFLOW = 20


"""
5. PREFETCH OPTIMIZATION
   - Adjust prefetch multiplier based on task duration
   - Short tasks: Higher prefetch
   - Long tasks: Lower prefetch
"""

# Short tasks (< 1 second)
SHORT_TASK_CONFIG = {
    "worker_prefetch_multiplier": 10
}

# Long tasks (> 1 minute)
LONG_TASK_CONFIG = {
    "worker_prefetch_multiplier": 1
}


"""
6. COMPRESSION
   - Compress large task arguments/results
   - Reduce network overhead
"""


@celery_app.task(
    name="celery_app.best_practices.compressed_task",
    compression="gzip"
)
def compressed_task(large_data: dict):
    """
    Task with compressed data transfer.
    
    Good for large payloads.
    """
    # Process large data
    return large_data




BACKGROUND TASKS & QUEUE MANAGEMENT - TEIL 4
Production Deployment, Monitoring & Scaling

🚀 PRODUCTION DEPLOYMENT
1. Systemd Service Configuration
ini# /etc/systemd/system/celery-worker.service

[Unit]
Description=Celery Worker Service
After=network.target redis.service postgresql.service

[Service]
Type=forking
User=celery
Group=celery
WorkingDirectory=/opt/ocr-backend

# Environment
Environment="CELERY_BROKER_URL=redis://localhost:6379/0"
Environment="CELERY_RESULT_BACKEND=redis://localhost:6379/1"
Environment="PYTHONPATH=/opt/ocr-backend"

# Worker command
ExecStart=/opt/ocr-backend/venv/bin/celery -A celery_app.celery worker \
    --pidfile=/var/run/celery/worker.pid \
    --logfile=/var/log/celery/worker.log \
    --loglevel=INFO \
    --concurrency=4 \
    --queues=default,high_priority,ocr \
    --hostname=worker1@%h

# Restart policy
Restart=always
RestartSec=10s

# Resource limits
LimitNOFILE=65535
MemoryLimit=4G
CPUQuota=200%

# Security
PrivateTmp=true
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
ini# /etc/systemd/system/celery-beat.service

[Unit]
Description=Celery Beat Scheduler
After=network.target redis.service

[Service]
Type=simple
User=celery
Group=celery
WorkingDirectory=/opt/ocr-backend

# Environment
Environment="CELERY_BROKER_URL=redis://localhost:6379/0"
Environment="PYTHONPATH=/opt/ocr-backend"

# Beat command
ExecStart=/opt/ocr-backend/venv/bin/celery -A celery_app.celery beat \
    --pidfile=/var/run/celery/beat.pid \
    --logfile=/var/log/celery/beat.log \
    --loglevel=INFO \
    --schedule=/var/run/celery/celerybeat-schedule

# Restart policy
Restart=always
RestartSec=10s

[Install]
WantedBy=multi-user.target
bash# Setup and management commands

# Create celery user
sudo useradd -r -s /bin/false celery

# Create directories
sudo mkdir -p /var/log/celery
sudo mkdir -p /var/run/celery
sudo chown -R celery:celery /var/log/celery
sudo chown -R celery:celery /var/run/celery

# Enable and start services
sudo systemctl daemon-reload
sudo systemctl enable celery-worker.service
sudo systemctl enable celery-beat.service

sudo systemctl start celery-worker.service
sudo systemctl start celery-beat.service

# Check status
sudo systemctl status celery-worker.service
sudo systemctl status celery-beat.service

# View logs
sudo journalctl -u celery-worker.service -f
sudo journalctl -u celery-beat.service -f

# Restart services
sudo systemctl restart celery-worker.service
sudo systemctl restart celery-beat.service

# Stop services
sudo systemctl stop celery-worker.service
sudo systemctl stop celery-beat.service
2. Supervisor Configuration
ini# /etc/supervisor/conf.d/celery.conf

[program:celery-worker-default]
command=/opt/ocr-backend/venv/bin/celery -A celery_app.celery worker -Q default,high_priority -c 4 -n worker_default@%%h
directory=/opt/ocr-backend
user=celery
numprocs=1
stdout_logfile=/var/log/celery/worker-default.log
stderr_logfile=/var/log/celery/worker-default-error.log
autostart=true
autorestart=true
startsecs=10
stopwaitsecs=600
stopasgroup=true
killasgroup=true
priority=998

[program:celery-worker-ocr]
command=/opt/ocr-backend/venv/bin/celery -A celery_app.celery worker -Q ocr -c 2 -n worker_ocr@%%h
directory=/opt/ocr-backend
user=celery
numprocs=1
stdout_logfile=/var/log/celery/worker-ocr.log
stderr_logfile=/var/log/celery/worker-ocr-error.log
autostart=true
autorestart=true
startsecs=10
stopwaitsecs=600
stopasgroup=true
killasgroup=true
priority=998

[program:celery-worker-email]
command=/opt/ocr-backend/venv/bin/celery -A celery_app.celery worker -Q email -c 10 --pool=eventlet -n worker_email@%%h
directory=/opt/ocr-backend
user=celery
numprocs=1
stdout_logfile=/var/log/celery/worker-email.log
stderr_logfile=/var/log/celery/worker-email-error.log
autostart=true
autorestart=true
startsecs=10
stopwaitsecs=600
stopasgroup=true
killasgroup=true
priority=998

[program:celery-beat]
command=/opt/ocr-backend/venv/bin/celery -A celery_app.celery beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
directory=/opt/ocr-backend
user=celery
numprocs=1
stdout_logfile=/var/log/celery/beat.log
stderr_logfile=/var/log/celery/beat-error.log
autostart=true
autorestart=true
startsecs=10
stopasgroup=true
killasgroup=true
priority=999

[program:flower]
command=/opt/ocr-backend/venv/bin/celery -A celery_app.celery flower --port=5555 --basic_auth=admin:secure_password
directory=/opt/ocr-backend
user=celery
numprocs=1
stdout_logfile=/var/log/celery/flower.log
stderr_logfile=/var/log/celery/flower-error.log
autostart=true
autorestart=true
startsecs=10
priority=997

[group:celery]
programs=celery-worker-default,celery-worker-ocr,celery-worker-email,celery-beat,flower
bash# Supervisor management commands

# Install supervisor
sudo apt-get install supervisor

# Update configuration
sudo supervisorctl reread
sudo supervisorctl update

# Start all celery services
sudo supervisorctl start celery:*

# Check status
sudo supervisorctl status

# Restart specific worker
sudo supervisorctl restart celery:celery-worker-ocr

# Stop all
sudo supervisorctl stop celery:*

# View logs
sudo supervisorctl tail -f celery:celery-worker-default
3. Production Environment Variables
bash# /opt/ocr-backend/.env.production

# ============================================
# CELERY CONFIGURATION
# ============================================

# Broker
CELERY_BROKER_URL=redis://prod-redis-master:6379/0
CELERY_BROKER_POOL_LIMIT=100

# Result Backend
CELERY_RESULT_BACKEND=redis://prod-redis-master:6379/1

# Worker Settings
CELERY_WORKER_PREFETCH_MULTIPLIER=4
CELERY_WORKER_MAX_TASKS_PER_CHILD=5000
CELERY_WORKER_DISABLE_RATE_LIMITS=False

# Task Settings
CELERY_TASK_SERIALIZER=json
CELERY_RESULT_SERIALIZER=json
CELERY_ACCEPT_CONTENT=json
CELERY_TIMEZONE=UTC
CELERY_ENABLE_UTC=True

# Time Limits
CELERY_TASK_SOFT_TIME_LIMIT=300
CELERY_TASK_TIME_LIMIT=600

# Reliability
CELERY_TASK_ACKS_LATE=True
CELERY_TASK_REJECT_ON_WORKER_LOST=True

# Monitoring
CELERY_SEND_TASK_EVENTS=True
CELERY_WORKER_SEND_TASK_EVENTS=True

# ============================================
# REDIS CONFIGURATION
# ============================================

REDIS_HOST=prod-redis-master
REDIS_PORT=6379
REDIS_PASSWORD=secure_redis_password
REDIS_DB=0
REDIS_MAX_CONNECTIONS=100

# Redis Sentinel (for HA)
REDIS_SENTINEL_HOSTS=sentinel1:26379,sentinel2:26379,sentinel3:26379
REDIS_SENTINEL_SERVICE_NAME=mymaster

# ============================================
# DATABASE CONFIGURATION
# ============================================

DATABASE_URL=postgresql://celery_user:secure_password@prod-db:5432/ocr_db
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=40
DATABASE_POOL_RECYCLE=3600

# ============================================
# LOGGING
# ============================================

LOG_LEVEL=INFO
LOG_FORMAT=[%(asctime)s: %(levelname)s/%(processName)s] %(message)s
SENTRY_DSN=https://your-sentry-dsn@sentry.io/project-id

# ============================================
# MONITORING
# ============================================

PROMETHEUS_PORT=9090
FLOWER_PORT=5555
FLOWER_BASIC_AUTH=admin:secure_flower_password
4. Health Checks & Readiness Probes
python# backend/api/v1/health.py

from fastapi import APIRouter, HTTPException
from typing import Dict, Any
from datetime import datetime

from celery_app.celery import celery_app
from core.redis_client import redis_client
from database import SessionLocal


router = APIRouter()


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Basic health check endpoint.
    
    Used by load balancers and orchestrators.
    """
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/health/ready")
async def readiness_check() -> Dict[str, Any]:
    """
    Readiness check - verifies all dependencies.
    
    Returns:
        200 if ready to serve traffic
        503 if not ready
    """
    health_status = {
        "status": "ready",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {}
    }
    
    # Check database
    try:
        db = SessionLocal()
        from sqlalchemy import text
        db.execute(text("SELECT 1"))
        db.close()
        health_status["checks"]["database"] = "ok"
    except Exception as exc:
        health_status["checks"]["database"] = f"error: {str(exc)}"
        health_status["status"] = "not_ready"
    
    # Check Redis
    try:
        redis_client.ping()
        health_status["checks"]["redis"] = "ok"
    except Exception as exc:
        health_status["checks"]["redis"] = f"error: {str(exc)}"
        health_status["status"] = "not_ready"
    
    # Check Celery workers
    try:
        inspect = celery_app.control.inspect()
        active_workers = inspect.active()
        
        if active_workers and len(active_workers) > 0:
            health_status["checks"]["celery_workers"] = f"ok ({len(active_workers)} workers)"
        else:
            health_status["checks"]["celery_workers"] = "warning: no workers"
            health_status["status"] = "degraded"
    
    except Exception as exc:
        health_status["checks"]["celery_workers"] = f"error: {str(exc)}"
        health_status["status"] = "not_ready"
    
    # Return appropriate status code
    if health_status["status"] == "ready":
        return health_status
    else:
        raise HTTPException(status_code=503, detail=health_status)


@router.get("/health/live")
async def liveness_check() -> Dict[str, Any]:
    """
    Liveness check - verifies process is running.
    
    Lighter than readiness check.
    """
    return {
        "status": "alive",
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/health/celery")
async def celery_health_check() -> Dict[str, Any]:
    """
    Detailed Celery health check.
    """
    from celery_app.monitoring import celery_monitor
    
    try:
        stats = celery_monitor.get_system_stats()
        
        return {
            "status": "healthy",
            "workers": stats["workers"],
            "active_tasks": stats["active_tasks"],
            "scheduled_tasks": stats["scheduled_tasks"],
            "queues": stats["queues"],
            "timestamp": datetime.utcnow().isoformat()
        }
    
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unhealthy",
                "error": str(exc),
                "timestamp": datetime.utcnow().isoformat()
            }
        )

📊 MONITORING & ALERTING
1. Prometheus Metrics Export
python# backend/celery_app/monitoring/prometheus.py

from prometheus_client import Counter, Gauge, Histogram, Summary
from prometheus_client import start_http_server, REGISTRY
import logging


logger = logging.getLogger(__name__)


# ============================================
# METRICS DEFINITIONS
# ============================================

# Task execution metrics
task_started = Counter(
    'celery_task_started_total',
    'Total number of tasks started',
    ['task_name', 'queue']
)

task_succeeded = Counter(
    'celery_task_succeeded_total',
    'Total number of successful tasks',
    ['task_name', 'queue']
)

task_failed = Counter(
    'celery_task_failed_total',
    'Total number of failed tasks',
    ['task_name', 'queue', 'error_type']
)

task_retried = Counter(
    'celery_task_retried_total',
    'Total number of task retries',
    ['task_name', 'queue']
)

# Task duration metrics
task_duration = Histogram(
    'celery_task_duration_seconds',
    'Task execution duration in seconds',
    ['task_name', 'queue'],
    buckets=[0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 300.0, 600.0]
)

# Queue metrics
queue_length = Gauge(
    'celery_queue_length',
    'Number of tasks in queue',
    ['queue']
)

# Worker metrics
active_workers = Gauge(
    'celery_active_workers',
    'Number of active workers',
    ['hostname']
)

active_tasks = Gauge(
    'celery_active_tasks',
    'Number of currently executing tasks',
    ['worker', 'task_name']
)

# Resource metrics
worker_memory_usage = Gauge(
    'celery_worker_memory_bytes',
    'Worker memory usage in bytes',
    ['worker']
)

worker_cpu_usage = Gauge(
    'celery_worker_cpu_percent',
    'Worker CPU usage percentage',
    ['worker']
)


# ============================================
# METRICS COLLECTOR
# ============================================

class CeleryMetricsCollector:
    """
    Collects and exports Celery metrics to Prometheus.
    """
    
    @staticmethod
    def update_queue_metrics():
        """Update queue length metrics"""
        from celery_app.monitoring import celery_monitor
        from core.redis_client import redis_client
        
        queues = ["default", "high_priority", "low_priority", "ocr", "email"]
        
        for queue_name in queues:
            try:
                length = celery_monitor.get_queue_length(queue_name)
                queue_length.labels(queue=queue_name).set(length)
            except Exception as exc:
                logger.error(f"Failed to get queue length for {queue_name}: {exc}")
    
    @staticmethod
    def update_worker_metrics():
        """Update worker metrics"""
        from celery_app.celery import celery_app
        
        try:
            inspect = celery_app.control.inspect()
            
            # Active workers
            stats = inspect.stats()
            if stats:
                for worker, stat in stats.items():
                    active_workers.labels(hostname=worker).set(1)
            
            # Active tasks
            active = inspect.active()
            if active:
                for worker, tasks in active.items():
                    for task in tasks:
                        active_tasks.labels(
                            worker=worker,
                            task_name=task['name']
                        ).set(len(tasks))
        
        except Exception as exc:
            logger.error(f"Failed to update worker metrics: {exc}")
    
    @staticmethod
    def start_metrics_server(port: int = 9090):
        """Start Prometheus metrics HTTP server"""
        try:
            start_http_server(port)
            logger.info(f"Prometheus metrics server started on port {port}")
        except Exception as exc:
            logger.error(f"Failed to start metrics server: {exc}")


# ============================================
# CELERY SIGNAL HANDLERS FOR METRICS
# ============================================

from celery.signals import (
    task_prerun,
    task_postrun,
    task_failure,
    task_retry
)
import time


# Store task start times
task_start_times = {}


@task_prerun.connect
def task_prerun_handler(sender=None, task_id=None, task=None, **kwargs):
    """Record task start"""
    task_started.labels(
        task_name=task.name,
        queue=task.request.delivery_info.get('routing_key', 'default')
    ).inc()
    
    # Record start time
    task_start_times[task_id] = time.time()


@task_postrun.connect
def task_postrun_handler(sender=None, task_id=None, task=None, **kwargs):
    """Record task success"""
    task_succeeded.labels(
        task_name=task.name,
        queue=task.request.delivery_info.get('routing_key', 'default')
    ).inc()
    
    # Record duration
    if task_id in task_start_times:
        duration = time.time() - task_start_times[task_id]
        task_duration.labels(
            task_name=task.name,
            queue=task.request.delivery_info.get('routing_key', 'default')
        ).observe(duration)
        
        del task_start_times[task_id]


@task_failure.connect
def task_failure_handler(sender=None, task_id=None, exception=None, **kwargs):
    """Record task failure"""
    task_failed.labels(
        task_name=sender.name,
        queue=sender.request.delivery_info.get('routing_key', 'default'),
        error_type=type(exception).__name__
    ).inc()
    
    # Cleanup start time
    if task_id in task_start_times:
        del task_start_times[task_id]


@task_retry.connect
def task_retry_handler(sender=None, task_id=None, **kwargs):
    """Record task retry"""
    task_retried.labels(
        task_name=sender.name,
        queue=sender.request.delivery_info.get('routing_key', 'default')
    ).inc()
2. Grafana Dashboard Configuration
json{
  "dashboard": {
    "title": "Celery Monitoring Dashboard",
    "tags": ["celery", "background-tasks"],
    "timezone": "browser",
    "panels": [
      {
        "title": "Task Execution Rate",
        "targets": [
          {
            "expr": "rate(celery_task_started_total[5m])",
            "legendFormat": "{{task_name}}"
          }
        ],
        "type": "graph"
      },
      {
        "title": "Task Success vs Failure Rate",
        "targets": [
          {
            "expr": "rate(celery_task_succeeded_total[5m])",
            "legendFormat": "Success - {{task_name}}"
          },
          {
            "expr": "rate(celery_task_failed_total[5m])",
            "legendFormat": "Failed - {{task_name}}"
          }
        ],
        "type": "graph"
      },
      {
        "title": "Queue Lengths",
        "targets": [
          {
            "expr": "celery_queue_length",
            "legendFormat": "{{queue}}"
          }
        ],
        "type": "graph"
      },
      {
        "title": "Task Duration (p95)",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(celery_task_duration_seconds_bucket[5m]))",
            "legendFormat": "p95 - {{task_name}}"
          }
        ],
        "type": "graph"
      },
      {
        "title": "Active Workers",
        "targets": [
          {
            "expr": "celery_active_workers",
            "legendFormat": "{{hostname}}"
          }
        ],
        "type": "stat"
      },
      {
        "title": "Worker CPU Usage",
        "targets": [
          {
            "expr": "celery_worker_cpu_percent",
            "legendFormat": "{{worker}}"
          }
        ],
        "type": "graph"
      },
      {
        "title": "Worker Memory Usage",
        "targets": [
          {
            "expr": "celery_worker_memory_bytes / 1024 / 1024",
            "legendFormat": "{{worker}} MB"
          }
        ],
        "type": "graph"
      }
    ]
  }
}
3. Sentry Integration
python# backend/celery_app/sentry_integration.py

import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.redis import RedisIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
import logging

from core.config import settings


logger = logging.getLogger(__name__)


def init_sentry():
    """
    Initialize Sentry for error tracking.
    
    Integrates with:
    - Celery
    - Redis
    - SQLAlchemy
    """
    if not settings.SENTRY_DSN:
        logger.warning("Sentry DSN not configured, skipping initialization")
        return
    
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        
        # Integrations
        integrations=[
            CeleryIntegration(),
            RedisIntegration(),
            SqlalchemyIntegration(),
        ],
        
        # Performance monitoring
        traces_sample_rate=0.1,  # 10% of transactions
        
        # Environment
        environment=settings.ENVIRONMENT,
        
        # Release tracking
        release=settings.APP_VERSION,
        
        # Error filtering
        before_send=filter_errors,
        
        # User context
        send_default_pii=False,
    )
    
    logger.info("Sentry initialized successfully")


def filter_errors(event, hint):
    """
    Filter errors before sending to Sentry.
    
    Prevents sending noise and sensitive data.
    """
    # Ignore specific exceptions
    if 'exc_info' in hint:
        exc_type, exc_value, tb = hint['exc_info']
        
        # Ignore expected errors
        if isinstance(exc_value, (KeyboardInterrupt, SystemExit)):
            return None
        
        # Ignore specific error messages
        if "connection reset" in str(exc_value).lower():
            return None
    
    # Remove sensitive data
    if 'request' in event:
        # Remove authorization headers
        if 'headers' in event['request']:
            event['request']['headers'].pop('Authorization', None)
            event['request']['headers'].pop('Cookie', None)
    
    return event


# Custom context for Celery tasks
from celery.signals import task_prerun, task_postrun, task_failure


@task_prerun.connect
def sentry_task_prerun(sender=None, task_id=None, task=None, **kwargs):
    """Add task context to Sentry"""
    with sentry_sdk.configure_scope() as scope:
        scope.set_context("celery_task", {
            "task_id": task_id,
            "task_name": task.name,
            "queue": task.request.delivery_info.get('routing_key', 'default')
        })


@task_failure.connect
def sentry_task_failure(sender=None, task_id=None, exception=None, **kwargs):
    """Capture task failures in Sentry"""
    with sentry_sdk.push_scope() as scope:
        scope.set_tag("celery_task", sender.name)
        scope.set_tag("task_id", task_id)
        
        sentry_sdk.capture_exception(exception)
4. Alerting Rules
yaml# prometheus/alerts/celery_alerts.yml

groups:
  - name: celery_alerts
    interval: 30s
    rules:
      # High task failure rate
      - alert: CeleryHighFailureRate
        expr: |
          rate(celery_task_failed_total[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High Celery task failure rate"
          description: "Task {{ $labels.task_name }} has a failure rate of {{ $value }} tasks/sec"
      
      # Queue backing up
      - alert: CeleryQueueBacklog
        expr: |
          celery_queue_length > 1000
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Celery queue {{ $labels.queue }} is backing up"
          description: "Queue has {{ $value }} tasks waiting"
      
      # No active workers
      - alert: CeleryNoWorkers
        expr: |
          sum(celery_active_workers) == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "No active Celery workers"
          description: "All Celery workers are down"
      
      # Slow task execution
      - alert: CelerySlowTasks
        expr: |
          histogram_quantile(0.95, rate(celery_task_duration_seconds_bucket[5m])) > 300
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Slow Celery task execution"
          description: "Task {{ $labels.task_name }} p95 duration is {{ $value }}s"
      
      # High worker CPU usage
      - alert: CeleryHighCPU
        expr: |
          celery_worker_cpu_percent > 90
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High CPU usage on Celery worker"
          description: "Worker {{ $labels.worker }} CPU at {{ $value }}%"
      
      # High worker memory usage
      - alert: CeleryHighMemory
        expr: |
          celery_worker_memory_bytes / 1024 / 1024 / 1024 > 3
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High memory usage on Celery worker"
          description: "Worker {{ $labels.worker }} memory at {{ $value }}GB"

🔧 TROUBLESHOOTING
1. Common Issues & Solutions
python# backend/celery_app/troubleshooting/diagnostics.py

"""
CELERY TROUBLESHOOTING GUIDE

Common issues and their solutions.
"""

import logging
from typing import Dict, Any, List


logger = logging.getLogger(__name__)


class CeleryDiagnostics:
    """
    Diagnostic tools for Celery troubleshooting.
    """
    
    @staticmethod
    def check_broker_connection() -> Dict[str, Any]:
        """
        Check Redis broker connection.
        
        Common issues:
        - Redis not running
        - Wrong connection URL
        - Network issues
        - Authentication failures
        """
        from core.redis_client import redis_client
        
        result = {
            "status": "unknown",
            "issues": [],
            "recommendations": []
        }
        
        try:
            # Ping Redis
            redis_client.ping()
            result["status"] = "ok"
        
        except ConnectionError:
            result["status"] = "error"
            result["issues"].append("Cannot connect to Redis")
            result["recommendations"].extend([
                "Check if Redis is running: systemctl status redis",
                "Verify CELERY_BROKER_URL in configuration",
                "Check network connectivity",
                "Verify firewall rules"
            ])
        
        except Exception as exc:
            result["status"] = "error"
            result["issues"].append(f"Unexpected error: {exc}")
            result["recommendations"].append("Check Redis logs for errors")
        
        return result
    
    @staticmethod
    def check_worker_status() -> Dict[str, Any]:
        """
        Check worker status.
        
        Common issues:
        - No workers running
        - Workers crashed
        - Workers stuck
        - Configuration mismatch
        """
        from celery_app.celery import celery_app
        
        result = {
            "status": "unknown",
            "workers": [],
            "issues": [],
            "recommendations": []
        }
        
        try:
            inspect = celery_app.control.inspect()
            
            # Get active workers
            active = inspect.active()
            
            if not active:
                result["status"] = "error"
                result["issues"].append("No active workers found")
                result["recommendations"].extend([
                    "Start workers: celery -A celery_app.celery worker",
                    "Check worker logs for errors",
                    "Verify worker service status",
                    "Check if workers can connect to broker"
                ])
            else:
                result["status"] = "ok"
                result["workers"] = list(active.keys())
            
            # Check worker stats
            stats = inspect.stats()
            if stats:
                for worker, stat in stats.items():
                    if stat.get('pool', {}).get('max-concurrency', 0) == 0:
                        result["issues"].append(
                            f"Worker {worker} has zero concurrency"
                        )
        
        except Exception as exc:
            result["status"] = "error"
            result["issues"].append(f"Error checking workers: {exc}")
        
        return result
    
    @staticmethod
    def check_task_routing() -> Dict[str, Any]:
        """
        Check task routing configuration.
        
        Common issues:
        - Tasks going to wrong queue
        - Routing key mismatch
        - Queue not consumed
        """
        from celery_app.celery import celery_app
        
        result = {
            "status": "ok",
            "issues": [],
            "recommendations": []
        }
        
        try:
            inspect = celery_app.control.inspect()
            
            # Get registered tasks
            registered = inspect.registered()
            
            # Get active queues
            active_queues = inspect.active_queues()
            
            if registered and active_queues:
                # Check if all queues have workers
                configured_queues = set()
                for worker, queues in active_queues.items():
                    for queue in queues:
                        configured_queues.add(queue['name'])
                
                # Check task routes
                from celery_app.config import CeleryConfig
                
                for task_pattern, route in CeleryConfig.task_routes.items():
                    queue = route.get('queue')
                    if queue and queue not in configured_queues:
                        result["issues"].append(
                            f"No worker consuming queue: {queue}"
                        )
                        result["recommendations"].append(
                            f"Start worker for queue {queue}: "
                            f"celery -A celery_app.celery worker -Q {queue}"
                        )
        
        except Exception as exc:
            result["status"] = "error"
            result["issues"].append(f"Error checking routing: {exc}")
        
        return result
    
    @staticmethod
    def check_queue_backlogs() -> Dict[str, Any]:
        """
        Check for queue backlogs.
        
        Common issues:
        - Too many tasks queued
        - Workers too slow
        - Not enough workers
        """
        from celery_app.monitoring import celery_monitor
        
        result = {
            "status": "ok",
            "queues": {},
            "issues": [],
            "recommendations": []
        }
        
        queues = ["default", "high_priority", "low_priority", "ocr", "email"]
        
        for queue in queues:
            length = celery_monitor.get_queue_length(queue)
            result["queues"][queue] = length
            
            # Check for backlogs
            if length > 1000:
                result["status"] = "warning"
                result["issues"].append(
                    f"Queue {queue} has {length} tasks waiting"
                )
                result["recommendations"].extend([
                    f"Add more workers for queue {queue}",
                    "Check if tasks are failing and retrying",
                    "Review task execution time"
                ])
        
        return result
    
    @staticmethod
    def run_full_diagnostics() -> Dict[str, Any]:
        """
        Run full diagnostic check.
        
        Returns comprehensive health report.
        """
        return {
            "broker": CeleryDiagnostics.check_broker_connection(),
            "workers": CeleryDiagnostics.check_worker_status(),
            "routing": CeleryDiagnostics.check_task_routing(),
            "queues": CeleryDiagnostics.check_queue_backlogs()
        }


# CLI command for diagnostics
def run_diagnostics():
    """
    Run diagnostics from command line.
    
    Usage:
        python -m celery_app.troubleshooting.diagnostics
    """
    import json
    
    print("Running Celery diagnostics...\n")
    
    results = CeleryDiagnostics.run_full_diagnostics()
    
    print(json.dumps(results, indent=2))
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    all_ok = True
    for component, result in results.items():
        status = result.get("status", "unknown")
        print(f"{component.upper()}: {status}")
        
        if status != "ok":
            all_ok = False
            
            if result.get("issues"):
                print(f"  Issues:")
                for issue in result["issues"]:
                    print(f"    - {issue}")
            
            if result.get("recommendations"):
                print(f"  Recommendations:")
                for rec in result["recommendations"]:
                    print(f"    - {rec}")
        
        print()
    
    if all_ok:
        print("✅ All systems operational")
    else:
        print("⚠️  Issues detected - review recommendations above")


if __name__ == "__main__":
    run_diagnostics()
2. Debug Mode & Tools
python# backend/celery_app/troubleshooting/debug_tools.py

from celery import Celery
from celery_app.celery import celery_app
import logging


logger = logging.getLogger(__name__)


class CeleryDebugger:
    """
    Debug tools for Celery development.
    """
    
    @staticmethod
    def run_task_synchronously(task_name: str, *args, **kwargs):
        """
        Run task synchronously for debugging.
        
        Bypasses Celery and runs task directly.
        """
        from celery_app.celery import celery_app
        
        task = celery_app.tasks[task_name]
        
        logger.info(f"Running task {task_name} synchronously")
        
        try:
            result = task(*args, **kwargs)
            logger.info(f"Task completed: {result}")
            return result
        except Exception as exc:
            logger.error(f"Task failed: {exc}", exc_info=True)
            raise
    
    @staticmethod
    def inspect_task(task_id: str):
        """
        Inspect task state and result.
        """
        from celery.result import AsyncResult
        
        result = AsyncResult(task_id, app=celery_app)
        
        return {
            "task_id": task_id,
            "state": result.state,
            "result": result.result,
            "traceback": result.traceback,
            "info": result.info,
            "ready": result.ready(),
            "successful": result.successful() if result.ready() else None,
            "failed": result.failed() if result.ready() else None
        }
    
    @staticmethod
    def trace_task_execution(task_name: str, *args, **kwargs):
        """
        Trace task execution with detailed logging.
        """
        import sys
        import traceback
        
        def trace_calls(frame, event, arg):
            if event == 'call':
                code = frame.f_code
                logger.debug(
                    f"Call: {code.co_filename}:{frame.f_lineno} {code.co_name}"
                )
            return trace_calls
        
        # Set trace
        sys.settrace(trace_calls)
        
        try:
            result = CeleryDebugger.run_task_synchronously(
                task_name,
                *args,
                **kwargs
            )
            return result
        finally:
            sys.settrace(None)
    
    @staticmethod
    def profile_task(task_name: str, *args, **kwargs):
        """
        Profile task execution to find bottlenecks.
        """
        import cProfile
        import pstats
        import io
        
        profiler = cProfile.Profile()
        
        profiler.enable()
        
        try:
            result = CeleryDebugger.run_task_synchronously(
                task_name,
                *args,
                **kwargs
            )
        finally:
            profiler.disable()
        
        # Print stats
        s = io.StringIO()
        ps = pstats.Stats(profiler, stream=s).sort_stats('cumulative')
        ps.print_stats(20)  # Top 20 functions
        
        print(s.getvalue())
        
        return result


# Enable eager mode for testing
def enable_eager_mode():
    """
    Enable eager mode - tasks run synchronously.
    
    Use for testing only!
    """
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    
    logger.warning("Eager mode enabled - tasks will run synchronously")


def disable_eager_mode():
    """Disable eager mode"""
    celery_app.conf.task_always_eager = False
    celery_app.conf.task_eager_propagates = False
    
    logger.info("Eager mode disabled")

📈 SCALING STRATEGIES
1. Horizontal Scaling
yaml# kubernetes/celery-deployment.yml

apiVersion: apps/v1
kind: Deployment
metadata:
  name: celery-worker-default
  labels:
    app: celery-worker
    queue: default
spec:
  replicas: 3  # Horizontal scaling
  selector:
    matchLabels:
      app: celery-worker
      queue: default
  template:
    metadata:
      labels:
        app: celery-worker
        queue: default
    spec:
      containers:
      - name: celery-worker
        image: ocr-backend:latest
        command: 
          - celery
          - -A
          - celery_app.celery
          - worker
          - -Q
          - default,high_priority
          - -c
          - "4"
          - --loglevel=info
        env:
          - name: CELERY_BROKER_URL
            valueFrom:
              secretKeyRef:
                name: celery-secrets
                key: broker-url
          - name: CELERY_RESULT_BACKEND
            valueFrom:
              secretKeyRef:
                name: celery-secrets
                key: result-backend
        resources:
          requests:
            memory: "1Gi"
            cpu: "1"
          limits:
            memory: "2Gi"
            cpu: "2"
        livenessProbe:
          exec:
            command:
              - celery
              - -A
              - celery_app.celery
              - inspect
              - ping
          initialDelaySeconds: 30
          periodSeconds: 30
        readinessProbe:
          exec:
            command:
              - celery
              - -A
              - celery_app.celery
              - inspect
              - active
          initialDelaySeconds: 10
          periodSeconds: 10

---

apiVersion: v1
kind: Service
metadata:
  name: celery-worker-default
spec:
  selector:
    app: celery-worker
    queue: default
  ports:
    - protocol: TCP
      port: 9090
      targetPort: 9090
  type: ClusterIP
2. Auto-scaling with HPA
yaml# kubernetes/celery-hpa.yml

apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: celery-worker-autoscaler
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: celery-worker-default
  minReplicas: 2
  maxReplicas: 10
  metrics:
    # Scale based on CPU
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    
    # Scale based on memory
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80
    
    # Scale based on queue length (custom metric)
    - type: Pods
      pods:
        metric:
          name: celery_queue_length
        target:
          type: AverageValue
          averageValue: "100"
  
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
        - type: Percent
          value: 50
          periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: 0
      policies:
        - type: Percent
          value: 100
          periodSeconds: 30
        - type: Pods
          value: 2
          periodSeconds: 30
      selectPolicy: Max
3. Dynamic Worker Scaling
python# backend/celery_app/scaling/autoscaler.py

from celery_app.monitoring import celery_monitor
from typing import Dict, Any
import logging


logger = logging.getLogger(__name__)


class CeleryAutoscaler:
    """
    Auto-scaling logic for Celery workers.
    
    Scales workers based on:
    - Queue length
    - Worker utilization
    - Task processing rate
    """
    
    def __init__(
        self,
        min_workers: int = 2,
        max_workers: int = 10,
        scale_up_threshold: int = 100,
        scale_down_threshold: int = 10
    ):
        self.min_workers = min_workers
        self.max_workers = max_workers
        self.scale_up_threshold = scale_up_threshold
        self.scale_down_threshold = scale_down_threshold
    
    def get_scaling_decision(self, queue: str) -> Dict[str, Any]:
        """
        Determine if scaling is needed.
        
        Returns:
            dict with scaling decision and target count
        """
        # Get current metrics
        queue_length = celery_monitor.get_queue_length(queue)
        
        # Get current worker count
        stats = celery_monitor.get_worker_stats()
        current_workers = len(stats) if stats else 0
        
        decision = {
            "action": "none",
            "current_workers": current_workers,
            "target_workers": current_workers,
            "queue_length": queue_length,
            "reason": ""
        }
        
        # Scale up if queue is long
        if queue_length > self.scale_up_threshold:
            if current_workers < self.max_workers:
                target = min(
                    current_workers + 2,
                    self.max_workers
                )
                decision.update({
                    "action": "scale_up",
                    "target_workers": target,
                    "reason": f"Queue length ({queue_length}) exceeds threshold"
                })
        
        # Scale down if queue is small
        elif queue_length < self.scale_down_threshold:
            if current_workers > self.min_workers:
                target = max(
                    current_workers - 1,
                    self.min_workers
                )
                decision.update({
                    "action": "scale_down",
                    "target_workers": target,
                    "reason": f"Queue length ({queue_length}) below threshold"
                })
        
        logger.info(f"Scaling decision for {queue}: {decision}")
        
        return decision
    
    def execute_scaling(self, queue: str, decision: Dict[str, Any]):
        """
        Execute scaling decision.
        
        In Kubernetes, this would update the Deployment replicas.
        """
        if decision["action"] == "none":
            return
        
        # This is a placeholder - actual implementation depends on orchestrator
        logger.info(
            f"Executing {decision['action']} for {queue}: "
            f"{decision['current_workers']} -> {decision['target_workers']}"
        )
        
        # Example: Update Kubernetes deployment
        # kubectl scale deployment celery-worker-{queue} --replicas={target}

📚 QUICK REFERENCE & CHEAT SHEET
python"""
CELERY QUICK REFERENCE

1. STARTING WORKERS
   celery -A celery_app.celery worker -Q default -c 4 -n worker1@%h
   
2. STARTING BEAT
   celery -A celery_app.celery beat -l info
   
3. STARTING FLOWER
   celery -A celery_app.celery flower --port=5555
   
4. INSPECTING WORKERS
   celery -A celery_app.celery inspect active
   celery -A celery_app.celery inspect stats
   celery -A celery_app.celery inspect scheduled
   celery -A celery_app.celery inspect registered
   
5. CONTROLLING WORKERS
   celery -A celery_app.celery control shutdown
   celery -A celery_app.celery control pool restart
   celery -A celery_app.celery control pool grow 2
   celery -A celery_app.celery control pool shrink 2
   
6. TASK MANAGEMENT
   celery -A celery_app.celery purge  # Clear all tasks
   celery -A celery_app.celery revoke task-id
   
7. MONITORING
   celery -A celery_app.celery events  # Event viewer
   celery -A celery_app.celery status  # Worker status
   
8. MIGRATION
   celery -A celery_app.celery migrate  # Migrate tasks
   
9. SHELL
   celery -A celery_app.celery shell  # Interactive shell
   
10. MULTI
    celery multi start worker1 worker2 -A celery_app.celery
    celery multi stop worker1 worker2
    celery multi restart worker1 worker2
"""
