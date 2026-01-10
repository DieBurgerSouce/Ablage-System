# Dependencies

<!-- AUTO-MANAGED: dependencies -->
## Backend (Python 3.11+)

### Core Framework
| Package | Version | Purpose |
|---------|---------|---------|
| fastapi | 0.110+ | API Framework |
| uvicorn | latest | ASGI Server |
| celery | 5.3+ | Task Queue |
| redis | 7.x | Cache/Queue |

### Database
| Package | Version | Purpose |
|---------|---------|---------|
| sqlalchemy | 2.0+ | ORM (async mode) |
| alembic | latest | Migrations |
| asyncpg | latest | PostgreSQL async driver |
| pgvector | latest | Vector embeddings |

### OCR & ML
| Package | Version | Purpose |
|---------|---------|---------|
| torch | 2.x | PyTorch (CUDA 12.x) |
| transformers | latest | HuggingFace models |
| deepseek-vl | latest | DeepSeek-Janus-Pro |
| surya-ocr | 1.1+ | Surya OCR |
| docling | 1.0+ | Layout analysis |

### Utilities
| Package | Version | Purpose |
|---------|---------|---------|
| pydantic | 2.x | Validation |
| structlog | latest | Structured logging |
| httpx | latest | HTTP client |
| minio | latest | Object storage |

## Frontend (Node 18+)

### Core
| Package | Version | Purpose |
|---------|---------|---------|
| react | 18.x | UI Framework |
| typescript | 5.x | Type safety |
| vite | latest | Build tool |

### UI & State
| Package | Version | Purpose |
|---------|---------|---------|
| @tanstack/react-router | latest | Routing |
| @tanstack/react-query | latest | Server state |
| tailwindcss | 3.x | Styling |
| shadcn/ui | latest | Component library |

## Infrastructure

### Container
| Tool | Version | Purpose |
|------|---------|---------|
| docker | 24.x | Containerization |
| docker-compose | 2.x | Orchestration |
| nvidia-container-toolkit | latest | GPU support |

### Databases & Services
| Service | Version | Port |
|---------|---------|------|
| PostgreSQL | 16.x | 5433 |
| Redis | 7.x | 6380 |
| MinIO | latest | 9000/9001 |

### Monitoring
| Service | Version | Port |
|---------|---------|------|
| Grafana | latest | 3002 |
| Prometheus | latest | 9090 |
| Loki | latest | - |

## GPU Requirements

| Component | Requirement |
|-----------|-------------|
| GPU | NVIDIA RTX 4080 (16GB VRAM) |
| CUDA | 12.x |
| cuDNN | 8.9+ |
| Driver | 535+ |

<!-- /AUTO-MANAGED: dependencies -->

## Dependency Updates

Bei Updates beachten:
1. CUDA/PyTorch Kompatibilitaet pruefen
2. SQLAlchemy 2.0 async API verwenden
3. Pydantic v2 Syntax fuer Schemas
