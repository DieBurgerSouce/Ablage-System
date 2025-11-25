# Docker & Makefile Cheatsheet

## 🐳 Docker Development Commands

### Start/Stop Services

```bash
# Development Environment (with hot reload, debug tools)
make dev                          # Start all services
make dev-build                    # Rebuild and start
make dev-down                     # Stop all services
make dev-restart                  # Restart services

# Production Environment
make prod                         # Start production stack
make prod-build                   # Rebuild and start production
make prod-down                    # Stop production

# Individual Services
docker-compose up -d postgres     # Start only PostgreSQL
docker-compose up -d redis        # Start only Redis
docker-compose up -d backend worker  # Start backend + worker
```

### View Logs

```bash
# All Services
make logs                         # Follow all logs
make logs > output.log            # Save logs to file

# Specific Services
make logs-backend                 # Backend only
make logs-worker                  # Worker only
make logs-db                      # PostgreSQL only

# Manual (more control)
docker-compose logs -f backend    # Follow backend logs
docker-compose logs --tail=100 backend  # Last 100 lines
docker-compose logs --since=1h    # Last hour
```

### Service Status

```bash
make ps                           # Show running containers
make health                       # Check service health
make urls                         # Show all service URLs

# Detailed status
docker-compose ps                 # Container status
docker stats                      # Resource usage (live)
```

### Shell Access

```bash
# Application Shells
make shell-backend                # Backend container bash
make shell-worker                 # Worker container bash

# Database Shells
make shell-redis                  # Redis CLI
make db-shell                     # PostgreSQL shell (psql)

# Manual access
docker exec -it ablage-backend-dev /bin/bash
docker exec -it ablage-postgres-dev psql -U postgres -d ablage_ocr
```

## 🗄️ Database Commands

### Migrations

```bash
# Run Migrations
make db-migrate                   # Apply all pending migrations
docker-compose exec backend alembic upgrade head

# Create New Migration
make db-migrate-create MSG="add user table"
docker-compose exec backend alembic revision --autogenerate -m "add user table"

# Migration History
docker-compose exec backend alembic history
docker-compose exec backend alembic current
```

### Database Operations

```bash
# Reset Database (⚠️ DESTROYS ALL DATA!)
make db-reset                     # Interactive confirmation
./scripts/db-reset.sh

# Backup & Restore
make db-backup                    # Creates backup_YYYYMMDD_HHMMSS.sql
docker-compose exec postgres pg_dump -U postgres ablage_ocr > backup.sql

# Restore from backup
docker-compose exec -T postgres psql -U postgres -d ablage_ocr < backup.sql

# Database Shell Queries
make db-shell                     # Opens psql shell
# Then run SQL:
# \dt                             # List tables
# \d table_name                   # Describe table
# SELECT * FROM documents LIMIT 10;
```

### Database Management Tools

```bash
# pgAdmin (Web UI)
# Open: http://localhost:5050
# Login: dev@ablage.local / devpassword

# Connection details for pgAdmin:
# Host: postgres
# Port: 5432
# Database: ablage_ocr
# Username: postgres
# Password: postgres (or from .env)
```

## 🧪 Testing in Docker

```bash
# Run Tests in Container
make test                         # All tests
make test-cov                     # With coverage
make test-unit                    # Unit tests only
make test-gpu                     # GPU tests only

# Manual test execution
docker-compose exec backend pytest tests/ -v
docker-compose exec backend pytest tests/unit/ -v --cov=app
docker-compose exec worker pytest tests/ -m gpu -v

# Watch mode (auto-rerun on changes)
make test-watch
docker-compose exec backend pytest-watch tests/
```

## 🔧 Build & Images

```bash
# Build Images
make build                        # Build all images
make build-backend                # Backend only
make build-worker                 # Worker only

# Rebuild from scratch (no cache)
docker-compose build --no-cache

# Pull Latest Base Images
make pull                         # Update base images
docker-compose pull
```

## 🧹 Cleanup Commands

```bash
# Remove Containers & Volumes
make clean                        # Remove all (containers + volumes + cache)
make clean-volumes                # Remove volumes only (⚠️ DATA LOSS!)
make dev-down                     # Stop and remove containers (keeps volumes)

# Python Cache Cleanup
make clean-cache                  # Remove __pycache__, .pytest_cache, etc.

# Docker System Cleanup
docker system prune -af           # Remove all unused images, containers
docker volume prune               # Remove unused volumes
docker network prune              # Remove unused networks
```

## 🎯 GPU Commands

```bash
# GPU Status
make gpu-status                   # nvidia-smi output
make gpu-logs                     # Monitor GPU real-time (watch -n 1 nvidia-smi)

# Test GPU in Container
make gpu-test                     # Verify CUDA availability
docker-compose exec worker python -c "import torch; print(torch.cuda.is_available())"

# GPU Memory
nvidia-smi --query-gpu=memory.used,memory.total --format=csv
```

## 🔍 Debugging & Development

```bash
# Debug Ports (for VSCode/IDE)
# Backend debugpy:  localhost:5678
# Worker debugpy:   localhost:5679

# Attach debugger in VSCode:
# F5 → "Attach to Container: Backend"
# F5 → "Attach to Container: Worker"

# Manual debugging
docker-compose exec backend python -m pdb app/main.py

# Environment variables
docker-compose exec backend env   # Show all env vars
docker-compose exec backend printenv DATABASE_URL
```

## 📦 Development Tools in Docker

### Redis Commander (Redis UI)
```bash
# Open: http://localhost:8081
# No authentication required (dev environment)

# Manual Redis CLI
make shell-redis
# Then: KEYS *, GET key_name, etc.
```

### Flower (Celery Monitor)
```bash
# Open: http://localhost:5555
# Shows: Active tasks, completed tasks, workers, queues

# Manual task inspection
docker-compose exec worker celery -A app.workers.celery_app inspect active
docker-compose exec worker celery -A app.workers.celery_app inspect stats
```

### MinIO Console (Object Storage)
```bash
# Open: http://localhost:9001
# Login: dev / devpassword

# Manual MinIO client (mc)
docker exec -it ablage-minio-dev mc ls local/
docker exec -it ablage-minio-dev mc cat local/documents/file.pdf
```

## 🚀 Quick Workflows

### Fresh Start (New Day)
```bash
make dev                          # Start all services
make logs                         # Check logs
make health                       # Verify health
# Open http://localhost:8000/docs
```

### After Pulling Changes
```bash
git pull origin main
make dev-build                    # Rebuild with new code
make db-migrate                   # Apply new migrations
make test                         # Run tests
```

### Before Pushing Changes
```bash
make lint                         # Check code quality
make test                         # Run all tests
git add .
git commit -m "feat: ..."         # Hooks run automatically
git push
```

### Recreate Everything (Nuclear Option)
```bash
make recreate                     # Down + build + up
# Or manually:
make dev-down
make build
make dev
make db-migrate
```

## 📊 Monitoring & Logs

### Real-Time Monitoring
```bash
# Follow all logs
docker-compose logs -f

# Follow specific service
docker-compose logs -f backend

# Filter logs by string
docker-compose logs -f | grep ERROR
docker-compose logs -f backend | grep "document_id"

# Save logs to file
docker-compose logs --no-color > logs.txt
```

### Container Resource Usage
```bash
# Live resource monitoring
docker stats                      # All containers
docker stats ablage-backend-dev   # Specific container

# Container inspection
docker inspect ablage-backend-dev
docker top ablage-backend-dev
```

## 🔐 Environment & Configuration

### Environment Files
```bash
# Development
.env                              # Local environment (git-ignored)
.env.example                      # Template (committed)

# Docker Compose
docker-compose.yml                # Production config
docker-compose.dev.yml            # Development overrides

# Usage
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d
# Or use Makefile: make dev
```

### View Configuration
```bash
# Show resolved docker-compose config
docker-compose config

# Show environment variables in container
docker-compose exec backend env
docker-compose exec backend printenv | grep DB_
```

## 🆘 Troubleshooting

### Services Won't Start
```bash
# Check logs for errors
make logs

# Check if ports are already in use
netstat -an | grep 8000
netstat -an | grep 5432

# Remove conflicting containers
docker rm -f $(docker ps -aq)

# Nuclear option
make clean && make dev
```

### Database Connection Issues
```bash
# Check PostgreSQL is running
docker-compose ps postgres

# Check database logs
make logs-db

# Test connection manually
docker-compose exec postgres psql -U postgres -d ablage_ocr -c "SELECT 1;"

# Verify environment variables
docker-compose exec backend printenv | grep DB_
```

### GPU Not Available
```bash
# Check GPU outside container
nvidia-smi

# Check GPU in container
make gpu-test

# Verify Docker GPU support
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi

# Check docker-compose GPU config
docker-compose config | grep -A5 "devices"
```

### Disk Space Issues
```bash
# Check disk usage
docker system df

# Clean up
docker system prune -af --volumes
make clean

# Remove unused images
docker image prune -af
```

### Network Issues
```bash
# Recreate network
docker-compose down
docker network prune
docker-compose up -d

# Check network
docker network ls
docker network inspect ablage-system_ablage-network
```

## 📖 Makefile Complete Reference

```bash
make help                    # Show all available commands

# Development
make dev                     # Start dev environment
make dev-build              # Rebuild dev environment
make dev-down               # Stop dev environment
make dev-restart            # Restart dev environment

# Production
make prod                   # Start production
make prod-build             # Build production
make prod-down              # Stop production

# Logs
make logs                   # All logs
make logs-backend           # Backend logs
make logs-worker            # Worker logs
make logs-db                # Database logs

# Container Status
make ps                     # Show containers
make health                 # Health check
make urls                   # Show service URLs

# Build
make build                  # Build all
make build-backend          # Build backend
make build-worker           # Build worker
make pull                   # Pull base images

# Database
make db-migrate             # Run migrations
make db-migrate-create      # Create migration (MSG="...")
make db-reset               # Reset database
make db-shell               # PostgreSQL shell
make db-backup              # Backup database

# Testing
make test                   # All tests
make test-cov               # With coverage
make test-unit              # Unit tests
make test-gpu               # GPU tests
make test-watch             # Watch mode

# Code Quality
make lint                   # Lint code
make lint-fix               # Lint with auto-fix
make format                 # Format code

# Shell Access
make shell-backend          # Backend shell
make shell-worker           # Worker shell
make shell-redis            # Redis CLI

# Cleanup
make clean                  # Full cleanup
make clean-volumes          # Remove volumes
make clean-cache            # Remove Python cache

# GPU
make gpu-status             # Check GPU
make gpu-logs               # Monitor GPU
make gpu-test               # Test GPU

# Setup
make setup                  # Initial setup
make hooks                  # Setup Git hooks

# Utility
make install                # Install dependencies
make update                 # Update dependencies
make recreate               # Recreate environment
```

---

**Tip**: Add `alias m='make'` to your shell for even faster commands!

**Pro Tip**: Use `make` + Tab completion to see all available targets.
