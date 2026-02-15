# Dependencies

## Tech Stack

### Python (Backend)
| Package | Version | Purpose |
|---------|---------|---------|
| fastapi | 0.110+ | API Framework |
| pydantic | 2.6+ | Validation |
| sqlalchemy | 2.0+ | ORM (async) |
| celery | 5.3+ | Task Queue |
| alembic | 1.13+ | Database Migrations |
| redis | 7.x | Cache/Queue |
| postgresql | 16+ | Database |
| aiohttp | 3.9.0+ | Async HTTP Client (Peppol/External) |
| reportlab | 4.0.9 | PDF Generation (mit rlPyCairo) |
| imagehash | 4.3.1+ | Perceptual Hashing (Visual Duplicate Detection) |
| scikit-learn | 1.3.0+ | TF-IDF + Cosine (Text Duplicate Detection) |

### Frontend
| Package | Version | Purpose |
|---------|---------|---------|
| react | 18.x | UI Framework |
| typescript | 5.x | Type Safety |
| @tanstack/react-router | Latest | Routing |
| @tanstack/react-query | Latest | State Management |
| shadcn/ui | Latest | UI Components |
| tailwindcss | 3.x | Styling |

### Infrastructure
| Component | Version | Purpose |
|-----------|---------|---------|
| Docker | Latest | Containerization |
| Nginx | Latest | Web Server |
| CUDA | 12.x | GPU Acceleration |
| NVIDIA Driver | Latest | GPU Support |

### Monitoring & Observability (2026-02-09)
| Component | Version | Purpose |
|-----------|---------|---------|
| Prometheus | Latest | Metrics Collection |
| Grafana | Latest | Metrics Visualization |
| Jaeger | 1.53 | Distributed Tracing (OpenTelemetry) |
| OpenTelemetry | Latest | OTLP gRPC Export (:4317) |
| Loki | Latest | Log Aggregation |
