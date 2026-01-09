# Event-Driven Architecture Guide

> **Status**: Production-Ready
> **Version**: 1.0
> **Letzte Aktualisierung**: Januar 2026
> **Zielgruppe**: Backend-Entwickler, Architekten, DevOps

## Übersicht

Das Ablage-System implementiert eine **umfassende Event-Driven Architecture (EDA)** für asynchrone Verarbeitung, Echtzeit-Kommunikation und lose gekoppelte Systemkomponenten. Diese Dokumentation beschreibt die verschiedenen Event-Patterns und deren Implementierung.

### Architektur-Überblick

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        EVENT-DRIVEN ARCHITECTURE                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐                   │
│  │   FastAPI   │────▶│   Celery    │────▶│   Workers   │                   │
│  │   Backend   │     │   Queue     │     │   (GPU/CPU) │                   │
│  └──────┬──────┘     └──────┬──────┘     └──────┬──────┘                   │
│         │                   │                   │                          │
│         ▼                   ▼                   ▼                          │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐                   │
│  │  WebSocket  │     │   Redis     │     │   Celery    │                   │
│  │  Manager    │     │   Pub/Sub   │     │   Signals   │                   │
│  └──────┬──────┘     └──────┬──────┘     └──────┬──────┘                   │
│         │                   │                   │                          │
│         ▼                   ▼                   ▼                          │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐                   │
│  │  Real-time  │     │   Event     │     │  Webhook    │                   │
│  │  Frontend   │     │  Listeners  │     │  Dispatcher │                   │
│  └─────────────┘     └─────────────┘     └─────────────┘                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. Celery Task Events & Signals

### 1.1 Signal-Handler-System

Das Celery-System nutzt Signals für Cross-Cutting Concerns wie Monitoring und Metriken.

**Referenz**: `app/workers/celery_app.py:1004-1110`

```python
from celery.signals import (
    task_prerun, task_postrun, task_failure, task_retry, task_success,
    worker_ready, worker_shutdown, celeryd_init
)

@task_prerun.connect
def task_prerun_handler(
    sender: Optional[Task] = None,
    task_id: Optional[str] = None,
    task: Optional[Task] = None,
    args: Optional[tuple] = None,
    kwargs: Optional[dict] = None,
    **extra: Any
) -> None:
    """Log task start and update database status."""
    task_name = task.name if task else "unknown"
    queue = getattr(task.request, 'delivery_info', {}).get('routing_key', 'default')

    logger.info("task_starting", task_id=task_id, task_name=task_name)

    # Prometheus Metriken
    record_task_started(task_id or "unknown", task_name, queue)
```

### 1.2 Verfügbare Celery Signals

| Signal | Trigger | Verwendung |
|--------|---------|------------|
| `task_prerun` | Vor Task-Ausführung | Metriken, Logging, GPU Lock |
| `task_postrun` | Nach Task-Ausführung | Cleanup, Metriken |
| `task_success` | Bei erfolgreichem Task | Success-Callbacks |
| `task_failure` | Bei Task-Fehler | Error-Recovery, OOM-Handler |
| `task_retry` | Bei Task-Retry | Retry-Tracking |
| `worker_ready` | Worker gestartet | Model-Preloading |
| `worker_shutdown` | Worker wird beendet | GPU-Cleanup |

### 1.3 GPU Task Lifecycle Events

```python
class GPUTask(Task):
    """Base task class for GPU-intensive operations."""

    def before_start(self, task_id: str, args: tuple, kwargs: dict) -> None:
        """Acquire GPU resources before task execution."""
        logger.info("gpu_task_starting", task_id=task_id, task_name=self.name)

        if torch.cuda.is_available():
            self._current_lock_value = acquire_gpu_lock()
            self._last_lock_refresh = time.time()

    def after_return(
        self, status: str, retval: Any, task_id: str,
        args: tuple, kwargs: dict, einfo: Optional[Any]
    ) -> None:
        """Release GPU resources after task completion."""
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        if self._current_lock_value:
            release_gpu_lock(self._current_lock_value)
            self._current_lock_value = None
```

### 1.4 Worker Startup Events (Model Preloading)

**Referenz**: `app/workers/celery_app.py:1120-1186`

```python
@worker_ready.connect
def preload_ocr_models(sender: Any = None, **kwargs: Any) -> None:
    """
    Preload OCR models when worker starts to eliminate cold start latency.

    Cold start problem:
    - First inference takes 60-90 seconds (CUDA kernel compilation)
    - Subsequent inferences are fast (~2-5 seconds)

    Solution:
    - Load models at worker startup
    - Run warm-up inference with dummy data
    - Models stay in GPU memory for fast subsequent processing
    """
    global _models_preloaded

    if _models_preloaded:
        return

    # Start Prometheus Metrics Server
    start_metrics_server(port=8001)

    # Initialize Worker Metrics
    hostname = sender.hostname if sender else os.environ.get("HOSTNAME", "unknown")
    init_worker_metrics(hostname=hostname, pool_size=1, prefetch=1)

    if torch.cuda.is_available():
        default_backend = settings.DEFAULT_OCR_BACKEND
        _preload_deepseek()  # or _preload_got_ocr(), _preload_surya_gpu()

    _models_preloaded = True
```

---

## 2. Webhook Event Dispatcher

### 2.1 Architektur

Das Webhook-System ermöglicht externe System-Integration durch ereignisbasierte HTTP-Callbacks.

**Referenz**: `app/services/webhook_dispatcher.py`

```
┌─────────────────────────────────────────────────────────────────┐
│                    WEBHOOK DISPATCHER                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐       │
│  │   System    │────▶│   Event     │────▶│  Matching   │       │
│  │   Event     │     │   Queue     │     │  Subs       │       │
│  └─────────────┘     └─────────────┘     └──────┬──────┘       │
│                                                  │              │
│                             ┌────────────────────┼───────────┐  │
│                             │                    ▼           │  │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐    │  │
│  │  Circuit    │◀───│   HTTP      │◀───│   HMAC      │    │  │
│  │  Breaker    │     │   Client    │     │   Sign      │    │  │
│  └─────────────┘     └─────────────┘     └─────────────┘    │  │
│                             │                                │  │
│                             ▼                                │  │
│  ┌─────────────┐     ┌─────────────┐                        │  │
│  │   Retry     │────▶│  Delivery   │                        │  │
│  │   Logic     │     │   Record    │                        │  │
│  └─────────────┘     └─────────────┘                        │  │
│                                                              │  │
│                      Exponential Backoff                     │  │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Webhook Event Types

**Referenz**: `app/services/webhook_dispatcher.py:38-62`

```python
class WebhookEventType(str, Enum):
    """Verfügbare Webhook-Event-Typen."""
    # Dokument-Events
    DOCUMENT_CREATED = "document.created"
    DOCUMENT_PROCESSED = "document.processed"
    DOCUMENT_FAILED = "document.failed"
    DOCUMENT_DELETED = "document.deleted"
    DOCUMENT_UPDATED = "document.updated"

    # OCR-Events
    OCR_STARTED = "ocr.started"
    OCR_COMPLETED = "ocr.completed"
    OCR_FAILED = "ocr.failed"
    OCR_QUALITY_WARNING = "ocr.quality_warning"

    # Batch-Events
    BATCH_STARTED = "batch.started"
    BATCH_COMPLETED = "batch.completed"
    BATCH_FAILED = "batch.failed"

    # System-Events
    SYSTEM_ALERT = "system.alert"
    BACKUP_COMPLETED = "backup.completed"
    SECURITY_INCIDENT = "security.incident"
```

### 2.3 Circuit Breaker Pattern

**Referenz**: `app/services/webhook_dispatcher.py:80-238`

Der Circuit Breaker schützt vor kaskadierten Fehlern bei nicht erreichbaren Webhook-Endpoints.

```python
class WebhookCircuitBreaker:
    """
    Circuit Breaker für Webhook-Zustellungen.

    States:
    - CLOSED: Normale Zustellung
    - OPEN: Webhooks blockiert (zu viele Fehler)
    - HALF_OPEN: Test-Phase nach Timeout
    """

    # Configuration
    FAILURE_THRESHOLD = 5      # Fehler bis zum Öffnen
    SUCCESS_THRESHOLD = 2      # Erfolge zum Schließen
    OPEN_TIMEOUT_SECONDS = 300  # 5 Minuten bis Half-Open
    HALF_OPEN_MAX_CALLS = 3    # Max gleichzeitige Test-Calls

    def get_state(self, url: str) -> CircuitState:
        """Get circuit state for URL."""
        state = self._states.get(url, CircuitState.CLOSED)

        # Check if OPEN circuit should transition to HALF_OPEN
        if state == CircuitState.OPEN:
            last_failure = self._last_failure_time.get(url)
            if last_failure:
                elapsed = (datetime.now(timezone.utc) - last_failure).total_seconds()
                if elapsed >= self.OPEN_TIMEOUT_SECONDS:
                    self._states[url] = CircuitState.HALF_OPEN
                    record_circuit_breaker_transition("open", "half_open")
                    return CircuitState.HALF_OPEN
        return state

    def record_success(self, url: str) -> None:
        """Record successful delivery."""
        state = self.get_state(url)

        if state == CircuitState.HALF_OPEN:
            self._success_counts[url] += 1
            if self._success_counts[url] >= self.SUCCESS_THRESHOLD:
                self._states[url] = CircuitState.CLOSED
                record_circuit_breaker_transition("half_open", "closed")
```

### 2.4 State Machine Diagramm

```
┌────────────────────────────────────────────────────────────────┐
│                   CIRCUIT BREAKER STATE MACHINE                │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│                    ┌─────────────────┐                         │
│      ┌────────────▶│     CLOSED      │◀────────────┐           │
│      │             │ (Normal Flow)   │             │           │
│      │             └────────┬────────┘             │           │
│      │                      │                      │           │
│      │          5 Failures  │                      │           │
│      │                      ▼                      │           │
│      │             ┌─────────────────┐             │           │
│      │             │      OPEN       │             │           │
│      │             │ (Blocking)      │             │ 2 Success │
│      │             └────────┬────────┘             │           │
│      │                      │                      │           │
│      │          5 Min       │                      │           │
│      │          Timeout     │                      │           │
│      │                      ▼                      │           │
│      │             ┌─────────────────┐             │           │
│      │  Failure    │    HALF_OPEN    │─────────────┘           │
│      └─────────────│ (Testing)       │                         │
│                    └─────────────────┘                         │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### 2.5 Event Dispatch mit Retry-Logik

```python
async def _deliver_webhook(
    self,
    db: AsyncSession,
    subscription: WebhookSubscription,
    payload: Dict[str, Any]
) -> bool:
    """Liefert Webhook mit Retry-Logik und Circuit Breaker."""

    # SSRF-Schutz - URL validieren
    is_valid, ssrf_error = await validate_url_for_ssrf_async(subscription.url)
    if not is_valid:
        return False

    # Circuit Breaker Check
    if not circuit_breaker.is_allowed(subscription.url):
        return False

    # Signatur erstellen (HMAC-SHA256)
    signature = self._sign_payload(payload_bytes, subscription.secret, timestamp)

    # Retry-Logik mit exponential backoff
    max_retries = subscription.max_retries or 3
    retry_delay = subscription.retry_delay_seconds or 60

    for attempt in range(max_retries + 1):
        try:
            response = await client.post(
                subscription.url,
                content=payload_bytes,
                headers=headers
            )

            if 200 <= response.status_code < 300:
                circuit_breaker.record_success(subscription.url)
                return True

            if 400 <= response.status_code < 500:
                # Client-Fehler - nicht retryable
                circuit_breaker.record_failure(subscription.url)
                return False

            # Server-Fehler - retry mit exponential backoff
            if attempt < max_retries:
                wait_time = retry_delay * (2 ** attempt)
                await asyncio.sleep(wait_time)

        except httpx.TimeoutException:
            if attempt < max_retries:
                await asyncio.sleep(retry_delay * (2 ** attempt))

    circuit_breaker.record_failure(subscription.url)
    return False
```

### 2.6 Convenience Functions

```python
async def dispatch_ocr_completed(
    db: AsyncSession,
    user_id: UUID,
    document_id: str,
    filename: str,
    backend: str,
    confidence: float,
    word_count: int,
    processing_time_ms: int
) -> int:
    """Dispatcht OCR-Completed Event."""
    return await dispatch_document_event(
        db=db,
        user_id=user_id,
        event_type=WebhookEventType.OCR_COMPLETED.value,
        document_id=document_id,
        filename=filename,
        backend=backend,
        confidence=confidence,
        word_count=word_count,
        processing_time_ms=processing_time_ms
    )
```

---

## 3. WebSocket Real-Time Events

### 3.1 Architektur

Das WebSocket-System ermöglicht bidirektionale Echtzeit-Kommunikation.

**Referenz**: `app/services/websocket_manager.py`

```
┌─────────────────────────────────────────────────────────────────┐
│                  WEBSOCKET CONNECTION MANAGER                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Session 1                    Session 2                         │
│  ┌─────────────┐              ┌─────────────┐                   │
│  │ User A      │              │ User C      │                   │
│  │ User B      │              │ User D      │                   │
│  └──────┬──────┘              └──────┬──────┘                   │
│         │                            │                          │
│         │      ┌────────────────┐    │                          │
│         └─────▶│  WS Manager    │◀───┘                          │
│                │  (Singleton)   │                               │
│                └───────┬────────┘                               │
│                        │                                        │
│         ┌──────────────┼──────────────┐                         │
│         ▼              ▼              ▼                         │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐               │
│  │  Broadcast  │ │  Presence   │ │  Typing     │               │
│  │  Messages   │ │  Tracking   │ │  Indicators │               │
│  └─────────────┘ └─────────────┘ └─────────────┘               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 WebSocket Message Types

**Referenz**: `app/services/websocket_manager.py:24-45`

```python
class WSMessageType(str, Enum):
    """WebSocket Nachrichten-Typen."""
    # Chat Messages
    NEW_MESSAGE = "new_message"
    MESSAGE_UPDATED = "message_updated"

    # Typing Indicators
    TYPING_START = "typing_start"
    TYPING_STOP = "typing_stop"

    # Presence
    PRESENCE_UPDATE = "presence"
    USER_JOINED = "user_joined"
    USER_LEFT = "user_left"

    # AI Streaming
    AI_STREAMING = "ai_streaming"
    AI_CHUNK = "ai_chunk"
    AI_DONE = "ai_done"

    # Errors
    ERROR = "error"
```

### 3.3 Connection Management

```python
class ChatWebSocketManager:
    """
    Manager für WebSocket-Verbindungen in Chat Sessions.

    Features:
    - Multi-User pro Session
    - Broadcast an alle Session-Teilnehmer
    - Typing-Indikatoren mit Debouncing
    - Presence-Tracking
    - AI-Streaming-Weiterleitung
    """

    def __init__(self):
        # session_id -> {user_id -> ConnectionInfo}
        self._connections: Dict[str, Dict[str, ConnectionInfo]] = {}
        # user_id -> Set[session_id] (User kann in mehreren Sessions sein)
        self._user_sessions: Dict[str, Set[str]] = {}
        # Lock für thread-safe Zugriff
        self._lock = asyncio.Lock()

    async def connect(
        self,
        websocket: WebSocket,
        session_id: str,
        user_id: str,
        username: str,
    ) -> bool:
        """Verbindet einen User mit einer Chat Session."""
        await websocket.accept()

        async with self._lock:
            # Session-Dict erstellen falls nicht vorhanden
            if session_id not in self._connections:
                self._connections[session_id] = {}

            # Alte Verbindung schließen falls vorhanden
            if user_id in self._connections[session_id]:
                old_conn = self._connections[session_id][user_id]
                await old_conn.websocket.close()

            # Neue Verbindung speichern
            self._connections[session_id][user_id] = ConnectionInfo(...)

        # User-joined Event an andere senden
        await self.broadcast_to_session(
            session_id=session_id,
            message={"type": WSMessageType.USER_JOINED.value, ...},
            exclude_user=user_id,
        )

        return True
```

### 3.4 Broadcast Patterns

```python
async def broadcast_to_session(
    self,
    session_id: str,
    message: Dict[str, Any],
    exclude_user: Optional[str] = None,
) -> None:
    """Sendet eine Nachricht an alle User in einer Session."""
    async with self._lock:
        if session_id not in self._connections:
            return
        connections = list(self._connections[session_id].items())

    # Außerhalb des Locks senden (non-blocking)
    for user_id, conn_info in connections:
        if exclude_user and user_id == exclude_user:
            continue
        try:
            await conn_info.websocket.send_json(message)
        except Exception as e:
            logger.warning("websocket_send_failed", ...)

async def broadcast_ai_chunk(
    self,
    session_id: str,
    chunk: str,
    message_id: Optional[str] = None,
) -> None:
    """Broadcastet einen AI-Streaming-Chunk."""
    await self.broadcast_to_session(
        session_id=session_id,
        message={
            "type": WSMessageType.AI_CHUNK.value,
            "chunk": chunk,
            "message_id": message_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
```

---

## 4. Redis Pub/Sub Events

### 4.1 Architektur

Redis Pub/Sub ermöglicht event-basierte Kommunikation zwischen Services.

**Referenz**: `app/core/redis_state.py:305-399`

```
┌─────────────────────────────────────────────────────────────────┐
│                    REDIS PUB/SUB ARCHITECTURE                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Publishers                                Subscribers          │
│  ┌─────────────┐                          ┌─────────────┐       │
│  │  Backend 1  │──┐                  ┌───▶│  Worker 1   │       │
│  └─────────────┘  │                  │    └─────────────┘       │
│  ┌─────────────┐  │    ┌────────┐    │    ┌─────────────┐       │
│  │  Backend 2  │──┼───▶│ Redis  │────┼───▶│  Worker 2   │       │
│  └─────────────┘  │    │ Pub/Sub│    │    └─────────────┘       │
│  ┌─────────────┐  │    └────────┘    │    ┌─────────────┐       │
│  │  Worker     │──┘                  └───▶│  Monitor    │       │
│  └─────────────┘                          └─────────────┘       │
│                                                                 │
│  Channels: events, ocr.*, document.*, workflow.*                │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 Event Publishing

```python
async def publish_event(
    self, event_type: str, data: Dict, channel: str = "events"
) -> int:
    """
    Publish event to Redis pub/sub.

    Args:
        event_type: Event type (document.uploaded, ocr.completed, etc.)
        data: Event data
        channel: Channel name

    Returns:
        Number of subscribers who received the message
    """
    await self._ensure_connection()

    event = {
        "type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }

    subscribers = await self._redis.publish(channel, json.dumps(event))

    logger.debug(
        "event_published",
        event_type=event_type,
        channel=channel,
        subscribers=subscribers
    )

    return subscribers
```

### 4.3 Event Subscription mit Cleanup

```python
async def subscribe_to_events(
    self, patterns: List[str], callback: callable,
    stop_event: Optional[asyncio.Event] = None
) -> None:
    """
    Subscribe to event patterns with cleanup support.

    Args:
        patterns: List of channel patterns (e.g., ['events', 'ocr.*'])
        callback: Async callback function(channel, message)
        stop_event: Optional event to signal subscription stop
    """
    await self._ensure_connection()

    pubsub = None
    try:
        pubsub = self._redis.pubsub()

        # Subscribe to patterns
        for pattern in patterns:
            await pubsub.psubscribe(pattern)

        # Listen for messages with stop support
        while True:
            if stop_event and stop_event.is_set():
                break

            message = await pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=1.0  # Check stop_event every second
            )

            if message and message["type"] == "pmessage":
                channel = message["channel"]
                data = json.loads(message["data"])
                await callback(channel, data)
    finally:
        if pubsub:
            await pubsub.punsubscribe()
            await pubsub.close()
```

### 4.4 Task Progress Tracking

```python
async def track_task_progress(
    self, task_id: str, progress: float, message: Optional[str] = None
) -> None:
    """
    Track task progress (0.0 to 1.0).

    Args:
        task_id: Task ID
        progress: Progress percentage (0.0-1.0)
        message: Optional status message
    """
    await self._ensure_connection()

    key = f"task:{task_id}:progress"
    data = {
        "progress": min(1.0, max(0.0, progress)),
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    await self._redis.setex(key, timedelta(hours=1), json.dumps(data))
```

### 4.5 Workflow State Persistence

```python
async def set_workflow_state(
    self, document_id: str, phase: str, state_data: Dict
) -> None:
    """
    Set workflow phase state.

    Args:
        document_id: Document ID
        phase: Workflow phase (classification, preprocessing, ocr, etc.)
        state_data: Phase state data
    """
    key = f"workflow:{document_id}"
    field = phase

    await self._redis.hset(key, field, json.dumps(state_data))
    await self._redis.expire(key, timedelta(days=7))  # 7 days retention
```

---

## 5. Priority Queue System

### 5.1 Queue-Konfiguration

**Referenz**: `app/workers/celery_app.py:303-440`

Das System verwendet priorisierte Queues für unterschiedliche Task-Typen.

```python
# Priority Queue Configuration
broker_transport_options = {
    "priority_steps": list(range(10)),  # 0-9 priority levels
    "sep": ":",
    "queue_order_strategy": "priority",  # Process high priority first
    "visibility_timeout": 43200,  # 12 hours
}
```

### 5.2 Queue-Hierarchie

```
┌─────────────────────────────────────────────────────────────────┐
│                       PRIORITY QUEUES                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Priority 9-10 (Höchste)                                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  ocr_high      - Einzeldokument OCR                      │   │
│  │  embedding_high - Embedding Generation                   │   │
│  │  extraction    - Quick Classification                    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  Priority 5-8 (Mittel)                                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  ocr_normal    - Batch OCR                               │   │
│  │  embedding_normal - Batch Embeddings                     │   │
│  │  validation    - Text Validation                         │   │
│  │  metadata      - Metadata Extraction                     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  Priority 1-4 (Niedrig)                                         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  maintenance   - Cleanup Tasks                           │   │
│  │  metrics       - System Metrics                          │   │
│  │  backup        - Backup Tasks                            │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  Dead Letter Queue (DLQ)                                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  dlq           - Fehlgeschlagene Tasks                   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 5.3 Task Routing

```python
task_routes = {
    # OCR tasks (GPU - High Priority)
    "app.workers.tasks.ocr_tasks.process_document_task": {
        "queue": "ocr_high",
        "priority": 9
    },
    "app.workers.tasks.ocr_tasks.batch_process_task": {
        "queue": "ocr_normal",
        "priority": 5
    },

    # Embedding tasks (GPU)
    "app.workers.tasks.embedding_tasks.generate_document_embedding": {
        "queue": "embedding_high",
        "priority": 8
    },

    # GDPR tasks (High Priority for Compliance)
    "app.workers.tasks.gdpr_tasks.send_breach_notification": {
        "queue": "maintenance",
        "priority": 9  # Höchste Priorität - GDPR Art. 33
    },

    # Maintenance tasks (Low Priority)
    "app.workers.tasks.cleanup_tasks.cleanup_soft_deleted_documents": {
        "queue": "maintenance",
        "priority": 1
    },
}
```

---

## 6. Dead Letter Queue (DLQ)

### 6.1 DLQ-Konfiguration

**Referenz**: `app/workers/celery_app.py:318-338`

```python
# DLQ Configuration
task_queues = {
    "dlq": {
        "exchange": "dlq",
        "routing_key": "dlq",
        "queue_arguments": {
            "x-max-priority": 10,
            "x-message-ttl": 604800000,  # 7 Tage TTL (ms)
        },
    },

    # Queues mit DLQ-Routing
    "ocr_high": {
        "exchange": "ocr_high",
        "routing_key": "ocr.high",
        "queue_arguments": {
            "x-max-priority": 10,
            "x-dead-letter-exchange": "dlq",
            "x-dead-letter-routing-key": "dlq",
        },
    },
    # ... weitere Queues
}

# DLQ Settings
task_reject_on_worker_lost = True
task_acks_on_failure_or_timeout = False  # Tasks bei Fehler rejected -> DLQ
```

### 6.2 DLQ Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│                    DEAD LETTER QUEUE FLOW                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐                                                │
│  │   Task      │                                                │
│  │   Queue     │                                                │
│  └──────┬──────┘                                                │
│         │                                                       │
│         ▼                                                       │
│  ┌─────────────┐     Success    ┌─────────────┐                │
│  │   Worker    │───────────────▶│   Result    │                │
│  │   Process   │                │   Backend   │                │
│  └──────┬──────┘                └─────────────┘                │
│         │                                                       │
│         │ Failure (after max_retries)                           │
│         ▼                                                       │
│  ┌─────────────┐                                                │
│  │     DLQ     │◀─── x-dead-letter-exchange                     │
│  │   (7 Tage)  │                                                │
│  └──────┬──────┘                                                │
│         │                                                       │
│         ├──────▶ Inspection (API)                               │
│         ├──────▶ Manual Retry                                   │
│         └──────▶ Auto-Cleanup (nach 7 Tagen)                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 7. Celery Beat Scheduled Events

### 7.1 Schedule-Konfiguration

**Referenz**: `app/workers/celery_app.py:443-720`

Das System verwendet Celery Beat für zeitgesteuerte Tasks.

```python
beat_schedule = {
    # OCR & Maintenance
    "cleanup-old-results": {
        "task": "app.workers.tasks.ocr_tasks.cleanup_task",
        "schedule": 3600.0,  # Stündlich
        "args": (24,),  # Cleanup älter als 24h
    },

    # Backup Tasks
    "backup-full-daily": {
        "task": "app.workers.tasks.backup_tasks.backup_full_task",
        "schedule": crontab(hour=2, minute=30),  # Täglich 02:30
    },

    # GDPR Compliance
    "gdpr-process-deletion-requests": {
        "task": "app.workers.tasks.gdpr_tasks.process_deletion_requests",
        "schedule": crontab(hour="*/6"),  # Alle 6 Stunden
    },

    # Worker Health
    "worker-health-check": {
        "task": "app.workers.tasks.monitoring_tasks.worker_health_check_task",
        "schedule": 60.0,  # Jede Minute
    },

    # ML/Drift Detection
    "ml-drift-detection": {
        "task": "app.workers.tasks.ml_tasks.run_drift_detection",
        "schedule": 3600.0,  # Stündlich
    },

    # Workflow Automation
    "workflow-check-scheduled": {
        "task": "workflow.check_scheduled",
        "schedule": 60.0,  # Jede Minute
    },
}
```

### 7.2 Schedule-Übersicht

| Task | Schedule | Beschreibung |
|------|----------|--------------|
| `cleanup_task` | Stündlich | OCR-Ergebnisse aufräumen |
| `backup_full_task` | Täglich 02:30 | Vollständiges Backup |
| `backup_retention` | Sonntag 03:00 | Alte Backups löschen |
| `gdpr_deletion` | Alle 6h | Löschanfragen verarbeiten |
| `worker_health_check` | Jede Minute | Worker-Status prüfen |
| `ml_drift_detection` | Stündlich | ML-Modell-Drift erkennen |
| `training_daily_stats` | Täglich 01:00 | Training-Statistiken |
| `surya_weekly_benchmark` | Sonntag 03:00 | OCR-Benchmark |

---

## 8. Progress Callback Pattern

### 8.1 Verwendung in Batch-Operationen

**Referenz**: `app/services/batch_processor.py:528-575`

```python
async def process_batch(
    self,
    documents: List[Document],
    backend: str = "auto",
    progress_callback: Optional[callable] = None,
) -> BatchResult:
    """
    Verarbeitet Batch mit Progress-Callback.

    Args:
        documents: Liste der Dokumente
        backend: OCR-Backend
        progress_callback: Optional callback für Progress-Updates
    """
    total = len(documents)

    for index, document in enumerate(documents):
        # Dokument verarbeiten
        result = await self._process_single(document, backend)

        # Progress-Callback aufrufen
        if progress_callback:
            progress = (index + 1) / total
            await progress_callback({
                "progress": progress,
                "current": index + 1,
                "total": total,
                "document_id": document.id,
                "status": result.status,
            })

    return batch_result
```

### 8.2 Verwendung in Migration-Services

**Referenz**: `app/services/rag/vector_sync_service.py:375-485`

```python
async def migrate_to_qdrant(
    self,
    batch_size: int = 100,
    progress_callback: Optional[Callable[[MigrationProgress], Awaitable[None]]] = None
) -> MigrationResult:
    """
    Migriert Embeddings zu Qdrant mit Progress-Tracking.

    Args:
        batch_size: Batch-Größe für Migration
        progress_callback: Optionaler Callback für Progress-Updates
    """
    # ... Migration Logic ...

    for batch in batches:
        # Batch verarbeiten
        await self._process_migration_batch(batch)

        # Progress-Callback aufrufen
        if progress_callback:
            await progress_callback(self._migration_progress)

    return migration_result
```

---

## 9. OOM Recovery Events

### 9.1 Enhanced OOM Handler

**Referenz**: `app/workers/celery_app.py:1562-1663`

```python
@task_failure.connect
def enhanced_oom_recovery_handler(
    sender: Optional[Task] = None,
    task_id: Optional[str] = None,
    exception: Optional[Exception] = None,
    args: Optional[tuple] = None,
    kwargs: Optional[dict] = None,
    traceback: Optional[Any] = None,
    einfo: Optional[Any] = None,
    **extra: Any
) -> None:
    """
    Enhanced OOM recovery handler with GPU memory cleanup.

    Actions on OOM:
    1. Log detailed GPU memory state
    2. Clear CUDA cache
    3. Reset peak memory stats
    4. Trigger garbage collection
    5. Record metrics for monitoring
    """
    is_oom = (
        isinstance(exception, torch.cuda.OutOfMemoryError)
        or (exception and "out of memory" in str(exception).lower())
    )

    if is_oom:
        logger.error(
            "oom_recovery_triggered",
            task_id=task_id,
            task_name=task_name,
            error=str(exception)
        )

        if torch.cuda.is_available():
            # Log memory state before cleanup
            before_allocated = torch.cuda.memory_allocated() / (1024**3)

            # Aggressive cleanup
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
            torch.cuda.reset_peak_memory_stats()

            # Force garbage collection
            gc.collect()

            # Log recovery
            freed_gb = before_allocated - after_allocated
            logger.info(
                "oom_recovery_complete",
                task_id=task_id,
                freed_gb=round(freed_gb, 2),
            )

            # Update metrics
            record_gpu_oom(task_name)
            update_gpu_metrics()
```

---

## 10. Prometheus Metrics Events

### 10.1 Celery Metrics

**Referenz**: `app/workers/celery_metrics.py`

```python
# Task Counter
celery_tasks_total = Counter(
    "ablage_celery_tasks_total",
    "Gesamtzahl Celery Tasks nach Status",
    ["task_name", "queue", "status"],
    registry=CELERY_REGISTRY
)

# Task Duration Histogram
celery_task_duration_seconds = Histogram(
    "ablage_celery_task_duration_seconds",
    "Celery Task Dauer in Sekunden",
    ["task_name", "queue"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0],
    registry=CELERY_REGISTRY
)

# GPU Memory Gauge
celery_gpu_memory_bytes = Gauge(
    "ablage_celery_gpu_memory_bytes",
    "GPU Speicherverbrauch in Bytes",
    ["type"],  # allocated, reserved, total
    registry=CELERY_REGISTRY
)

# OOM Events Counter
celery_gpu_oom_events_total = Counter(
    "ablage_celery_gpu_oom_events_total",
    "Anzahl GPU Out-of-Memory Events",
    ["task_name"],
    registry=CELERY_REGISTRY
)
```

### 10.2 Metrics Recording Functions

```python
def record_task_started(task_id: str, task_name: str, queue: str) -> None:
    """Record task start event."""
    celery_tasks_total.labels(
        task_name=task_name,
        queue=queue,
        status="started"
    ).inc()
    celery_tasks_active.labels(task_name=task_name, queue=queue).inc()

def record_task_succeeded(task_id: str, task_name: str, queue: str) -> None:
    """Record task success event."""
    celery_tasks_total.labels(
        task_name=task_name,
        queue=queue,
        status="success"
    ).inc()
    celery_tasks_active.labels(task_name=task_name, queue=queue).dec()

def record_gpu_oom(task_name: str) -> None:
    """Record GPU OOM event."""
    celery_gpu_oom_events_total.labels(task_name=task_name).inc()
```

---

## 11. Best Practices

### 11.1 Event Design Guidelines

1. **Event Naming**: Verwende dot-notation (z.B. `document.processed`, `ocr.failed`)
2. **Event Payload**: Minimal aber vollständig - alle nötigen Daten für Handler
3. **Idempotenz**: Events sollten mehrfach verarbeitbar sein
4. **Versioning**: API-Version im Event-Payload inkludieren

### 11.2 Error Handling

```python
# Retry mit exponential backoff
@celery_app.task(
    bind=True,
    autoretry_for=(TransientError,),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True
)
def process_task(self, document_id: str):
    try:
        # Task Logic
        pass
    except PermanentError as e:
        # Nicht retryable - direkt zu DLQ
        raise
    except TransientError as e:
        # Auto-Retry durch autoretry_for
        raise
```

### 11.3 Monitoring Checklist

- [ ] Task-Counter (started, success, failed, retried)
- [ ] Task-Duration Histogramme
- [ ] GPU-Memory Gauges
- [ ] OOM-Events Counter
- [ ] Queue-Längen
- [ ] Circuit-Breaker States
- [ ] Worker-Health Status

---

## 12. Referenzen

### 12.1 Interne Dokumentation

- [Dependency-Injection-Pattern.md](./Dependency-Injection-Pattern.md)
- [GPU-Resource-Management.md](./GPU-Resource-Management.md) (noch zu erstellen)
- [Service-Integration-Map.md](./Service-Integration-Map.md) (noch zu erstellen)

### 12.2 Code-Referenzen

| Komponente | Datei | Zeilen |
|------------|-------|--------|
| Celery Signals | `app/workers/celery_app.py` | 1004-1110 |
| Webhook Dispatcher | `app/services/webhook_dispatcher.py` | 1-814 |
| WebSocket Manager | `app/services/websocket_manager.py` | 1-476 |
| Redis State Manager | `app/core/redis_state.py` | 1-399 |
| Celery Metrics | `app/workers/celery_metrics.py` | 1-150 |

### 12.3 Externe Ressourcen

- [Celery Signals Documentation](https://docs.celeryq.dev/en/stable/userguide/signals.html)
- [Redis Pub/Sub](https://redis.io/docs/manual/pubsub/)
- [Circuit Breaker Pattern](https://martinfowler.com/bliki/CircuitBreaker.html)
- [WebSocket RFC 6455](https://tools.ietf.org/html/rfc6455)
