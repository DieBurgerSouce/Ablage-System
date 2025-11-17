# Intelligent Document Processing System

A comprehensive multi-backend OCR and document processing system with intelligent routing and GPU acceleration.

## Overview

This project implements an intelligent document processing pipeline that automatically routes documents to the optimal OCR backend based on complexity, type, and resource availability. The system leverages GPU acceleration for complex documents while maintaining high throughput with CPU-based processing for simpler cases.

## Architecture

The system consists of multiple layers:

- **API Gateway Layer**: FastAPI-based REST interface with authentication, rate limiting, and request validation
- **Orchestrator Layer**: Intelligent routing engine that selects the optimal backend based on document complexity
- **Processing Backends**:
  - **GPU-A (DeepSeek-Janus-Pro)**: For complex documents with advanced understanding
  - **GPU-B (GOT-OCR 2.0)**: For fast, high-quality OCR
  - **CPU (Surya + Docling)**: Fallback and overflow handling
- **Post-Processing Pipeline**: Confidence scoring, validation, table normalization
- **Storage Layer**: PostgreSQL, Redis, MinIO/S3

## Technology Stack

### Core Framework
- **FastAPI 0.110+**: Async/await support, automatic documentation
- **Python 3.11+**: Modern type hints and ML library support

### Processing Backends
- **DeepSeek-Janus-Pro 1.3B**: Complex document understanding
- **GOT-OCR 2.0**: Fast OCR with 580M parameters
- **Surya OCR + Docling**: CPU-based processing for fallback

### Infrastructure
- **PostgreSQL 16+**: Primary database with pgvector and pg_trgm extensions
- **Redis 7.2+**: Queue management and caching
- **MinIO**: S3-compatible object storage
- **Prometheus + Grafana**: Monitoring and observability

## Features

- ✨ **Intelligent Routing**: Automatically selects the best backend based on document complexity
- 🚀 **GPU Acceleration**: Leverages CUDA for high-performance processing
- 📊 **Multi-Backend Support**: Falls back gracefully when GPUs are unavailable
- 🔄 **Background Processing**: Async job processing with status tracking
- 📈 **Monitoring**: Built-in metrics and health checks
- 🔐 **Security**: Authentication, rate limiting, and input validation
- 📦 **Scalable**: Designed for horizontal scaling

## Documentation

Comprehensive documentation is available in the `.claude/Docs/` directory:

### Core Documentation
- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture overview
- [CHANGELOG.md](CHANGELOG.md) - Version history and changes
- [CONTRIBUTING.md](CONTRIBUTING.md) - Contribution guidelines
- [CONVENTIONS.md](CONVENTIONS.md) - Code and documentation conventions
- [DEPLOYMENT.md](DEPLOYMENT.md) - Production deployment guide
- [TESTING.md](TESTING.md) - Testing strategy and guidelines
- [CLAUDE.md](CLAUDE.md) - Claude Code integration guide

### Detailed Guides
- [Mission & Overview](.claude/Docs/Guides/Mission.md)
- [Tech Stack Details](.claude/Docs/Guides/TechStack.md)
- [API Documentation](.claude/Docs/API/API_Documentation.md)
- [Frontend Architecture](.claude/Docs/Frontend-Architecture.md)
- [ML Model Management](.claude/Docs/ML-Model-Management.md)

### Development & Operations
- [Database Architecture](.claude/Docs/Guides/Database.md)
- [Development Setup](.claude/Docs/Guides/Development-Setup.md)
- [Deployment Guide](.claude/Docs/Guides/Deployment-Production.md)
- [Security & Authentication](.claude/Docs/Guides/Security&Authentication.md)
- [Testing Guide](.claude/Docs/Guides/Testing-Guide.md)
- [Error Handling & Logging](.claude/Docs/Guides/Error-Handling-Logging.md)

### Performance & Scaling
- [Database Performance Optimization](.claude/Docs/Guides/Database_Query_Performance_Optimization.md)
- [Caching Strategy](.claude/Docs/Guides/Caching-Strategy.md)
- [Rate Limiting Guide](.claude/Docs/Guides/Rate-Limiting-Guide.md)
- [Scalability Guide](.claude/Docs/Guides/Scalability-Guide.md)

### Infrastructure & Operations
- [File Storage Management](.claude/Docs/Guides/File-Storage-Management.md)
- [Infrastructure as Code](.claude/Docs/Guides/Infrastructure-as-Code.md)
- [Backup & Recovery](.claude/Docs/Guides/Backup-Recovery-Guide.md)
- [Disaster Recovery](.claude/Docs/Guides/Disaster-Recovery.md)
- [Monitoring & Metrics](.claude/Docs/Guides/Metrics-Monitoring-Guide.md)
- [Troubleshooting Guide](.claude/Docs/Guides/Troubleshooting-Guide.md)

### Advanced Topics
- [API Client SDK](.claude/Docs/Guides/API-Client-SDK.md)
- [Webhooks Guide](.claude/Docs/Guides/Webhooks-Guide.md)
- [Migration Guide](.claude/Docs/Guides/Migration-Guide.md)
- [Data Pipeline Guide](.claude/Docs/Guides/Data-Pipeline-Guide.md)
- [Notification System](.claude/Docs/Guides/Notification-System.md)
- [Background Tasks](.claude/Docs/Guides/Background-Tasks.md)

📚 [Browse all documentation](.claude/Docs/README.md)

## Quick Start

### Prerequisites
- Python 3.11+
- CUDA 12.1+ (for GPU backends)
- 16GB+ RAM
- 16GB+ VRAM (for GPU processing)

### Installation

```bash
# Clone the repository
git clone https://github.com/DieBurgerSouce/intelligent-document-processing.git
cd intelligent-document-processing

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your configuration

# Run database migrations
alembic upgrade head

# Start the server
uvicorn api.main:app --reload
```

### Basic Usage

```python
import requests

# Upload a document for processing
with open('invoice.pdf', 'rb') as f:
    response = requests.post(
        'http://localhost:8000/api/v1/ocr/process',
        files={'file': f},
        data={
            'document_type': 'invoice',
            'complexity': 'moderate'
        }
    )

job_id = response.json()['job_id']

# Check processing status
status = requests.get(f'http://localhost:8000/api/v1/ocr/status/{job_id}')
print(status.json())
```

## Performance

- **GPU-A (DeepSeek)**: 1-2 seconds per page for complex documents
- **GPU-B (GOT-OCR)**: 0.3-0.5 seconds per page for standard OCR
- **CPU (Surya)**: 3-5 seconds per page, 720-1200 pages/hour throughput

## Hardware Requirements

### Minimal Setup
- CPU: 4+ cores
- RAM: 16GB
- Storage: 50GB

### Recommended Setup
- CPU: 8+ cores
- RAM: 64GB
- GPU: NVIDIA with 16GB+ VRAM (RTX 4080/4090, A4000, etc.)
- Storage: 500GB SSD

## Contributing

Contributions are welcome! Please see our contributing guidelines for more details.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- DeepSeek AI for the Janus-Pro model
- GOT-OCR 2.0 team
- Surya OCR and Docling projects
- FastAPI and the Python community

## Support

For questions, issues, or feature requests, please open an issue on GitHub.
