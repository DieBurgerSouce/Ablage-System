# Local Development Setup Guide
**Ablage-System Document Processing Platform**
**Version:** 1.0
**Last Updated:** 2025-01-23

---

## 📑 Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Quick Start (5 Minutes)](#quick-start-5-minutes)
4. [Detailed Setup](#detailed-setup)
5. [IDE Configuration](#ide-configuration)
6. [Running Services](#running-services)
7. [Database Setup](#database-setup)
8. [Running Tests](#running-tests)
9. [Debugging](#debugging)
10. [Common Issues](#common-issues)
11. [Development Workflow](#development-workflow)
12. [Useful Commands](#useful-commands)

---

## Overview

This guide helps you set up a complete local development environment for the Ablage-System. By the end, you'll have:

- ✅ Backend API running with hot reload
- ✅ Worker process with GPU support (if available)
- ✅ PostgreSQL, Redis, and MinIO running locally
- ✅ Frontend dev server with HMR (Hot Module Replacement)
- ✅ Pre-commit hooks configured
- ✅ Tests passing

**Time to Setup:** ~15 minutes (first time), ~5 minutes (subsequent)

---

## Prerequisites

### Required Software

#### 1. Python 3.11+
```bash
# Check Python version
python --version  # Should be 3.11 or higher

# Install Python 3.11 if needed
# Ubuntu/Debian
sudo apt update
sudo apt install python3.11 python3.11-venv python3.11-dev

# macOS (using Homebrew)
brew install python@3.11

# Windows
# Download from python.org and install
```

#### 2. Node.js 20+
```bash
# Check Node version
node --version  # Should be 20.x or higher

# Install Node.js
# Ubuntu/Debian
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# macOS (using Homebrew)
brew install node@20

# Windows
# Download from nodejs.org and install
```

#### 3. Docker & Docker Compose
```bash
# Check Docker
docker --version  # Should be 24.x or higher
docker compose version  # Should be 2.x or higher

# Install Docker
# Ubuntu/Debian
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER  # Add user to docker group

# macOS
# Download Docker Desktop from docker.com

# Windows
# Download Docker Desktop from docker.com
```

#### 4. Git
```bash
# Check Git
git --version

# Install Git
# Ubuntu/Debian
sudo apt install git

# macOS
brew install git

# Windows
# Download from git-scm.com
```

### Optional but Recommended

#### 1. NVIDIA GPU (for OCR workers)
```bash
# Check if NVIDIA GPU is available
nvidia-smi

# Install NVIDIA Docker support (Ubuntu)
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
  sudo tee /etc/apt/sources.list.d/nvidia-docker.list

sudo apt-get update
sudo apt-get install -y nvidia-docker2
sudo systemctl restart docker
```

#### 2. Useful Tools
```bash
# PostgreSQL client (psql)
sudo apt install postgresql-client  # Ubuntu/Debian
brew install postgresql@16  # macOS

# Redis client (redis-cli)
sudo apt install redis-tools  # Ubuntu/Debian
brew install redis  # macOS

# HTTPie (API testing)
pip install httpie

# jq (JSON parsing)
sudo apt install jq  # Ubuntu/Debian
brew install jq  # macOS
```

---

## Quick Start (5 Minutes)

For experienced developers who want to get up and running immediately:

```bash
# 1. Clone repository
git clone https://github.com/your-org/ablage-system.git
cd ablage-system

# 2. Run setup script
./scripts/dev-setup.sh

# 3. Start services
docker compose up -d postgres redis minio

# 4. Run database migrations
python -m alembic upgrade head

# 5. Start backend (with hot reload)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 6. In another terminal, start frontend
cd frontend
npm run dev

# 7. Open browser
# Frontend: http://localhost:3000
# API docs: http://localhost:8000/docs
```

That's it! Continue reading for detailed setup and troubleshooting.

---

## Detailed Setup

### Step 1: Clone Repository

```bash
# Clone via HTTPS
git clone https://github.com/your-org/ablage-system.git

# Or via SSH (if you have SSH keys configured)
git clone git@github.com:your-org/ablage-system.git

# Navigate to project directory
cd ablage-system

# Check current branch
git branch
# Should show: * main
```

### Step 2: Backend Setup

#### Create Virtual Environment

```bash
# Create virtual environment
python3.11 -m venv venv

# Activate virtual environment
# Linux/macOS
source venv/bin/activate

# Windows (PowerShell)
.\venv\Scripts\Activate.ps1

# Windows (Command Prompt)
venv\Scripts\activate.bat

# Verify activation (should show path to venv)
which python  # Linux/macOS
where python  # Windows
```

#### Install Python Dependencies

```bash
# Upgrade pip
pip install --upgrade pip

# Install production dependencies
pip install -r requirements.txt

# Install development dependencies
pip install -r requirements-dev.txt

# Verify installation
pip list

# Important packages to verify:
# - fastapi >= 0.110.0
# - sqlalchemy >= 2.0.25
# - alembic >= 1.13.1
# - celery >= 5.3.6
# - torch >= 2.1.0 (if GPU available)
```

#### Configure Environment Variables

```bash
# Copy example environment file
cp .env.example .env

# Edit .env file
nano .env  # or use your preferred editor

# Required variables:
# DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/ablage
# REDIS_URL=redis://localhost:6379/0
# MINIO_ENDPOINT=localhost:9000
# MINIO_ACCESS_KEY=minioadmin
# MINIO_SECRET_KEY=minioadmin
# JWT_SECRET_KEY=your-secret-key-change-in-production
# ENVIRONMENT=development
# LOG_LEVEL=debug
```

### Step 3: Frontend Setup

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Or use pnpm (faster)
npm install -g pnpm
pnpm install

# Verify installation
npm list vue
npm list @vitejs/plugin-vue

# Copy frontend environment file
cp .env.example .env.local

# Edit .env.local
nano .env.local

# Required variables:
# VITE_API_BASE_URL=http://localhost:8000/api/v1
# VITE_SOCKET_URL=http://localhost:8000
```

### Step 4: Pre-commit Hooks

```bash
# Install pre-commit
pip install pre-commit

# Install hooks
pre-commit install

# Test hooks (optional)
pre-commit run --all-files

# Hooks will now run automatically on git commit
```

---

## IDE Configuration

### Visual Studio Code

#### Install Extensions

```json
// .vscode/extensions.json
{
  "recommendations": [
    "ms-python.python",
    "ms-python.vscode-pylance",
    "ms-python.black-formatter",
    "charliermarsh.ruff",
    "Vue.volar",
    "dbaeumer.vscode-eslint",
    "esbenp.prettier-vscode",
    "ms-azuretools.vscode-docker",
    "redhat.vscode-yaml"
  ]
}
```

#### Workspace Settings

```json
// .vscode/settings.json
{
  // Python
  "python.defaultInterpreterPath": "${workspaceFolder}/venv/bin/python",
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": false,
  "python.linting.flake8Enabled": false,
  "python.linting.ruffEnabled": true,
  "python.formatting.provider": "black",
  "python.testing.pytestEnabled": true,
  "python.testing.pytestArgs": [
    "tests"
  ],

  // Editor
  "editor.formatOnSave": true,
  "editor.codeActionsOnSave": {
    "source.fixAll.eslint": true,
    "source.organizeImports": true
  },

  // Files
  "files.exclude": {
    "**/__pycache__": true,
    "**/*.pyc": true,
    "**/.pytest_cache": true,
    "**/.mypy_cache": true,
    "**/node_modules": true,
    "**/dist": true
  },

  // TypeScript/Vue
  "typescript.tsdk": "frontend/node_modules/typescript/lib",
  "volar.typescript.tsdk": "frontend/node_modules/typescript/lib"
}
```

#### Debug Configuration

```json
// .vscode/launch.json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Python: FastAPI",
      "type": "python",
      "request": "launch",
      "module": "uvicorn",
      "args": [
        "app.main:app",
        "--reload",
        "--host",
        "0.0.0.0",
        "--port",
        "8000"
      ],
      "jinja": true,
      "justMyCode": false,
      "env": {
        "ENVIRONMENT": "development"
      }
    },
    {
      "name": "Python: Celery Worker",
      "type": "python",
      "request": "launch",
      "module": "celery",
      "args": [
        "-A",
        "app.celery",
        "worker",
        "--loglevel=debug",
        "--concurrency=1",
        "--pool=solo"
      ],
      "console": "integratedTerminal"
    },
    {
      "name": "Python: Current File",
      "type": "python",
      "request": "launch",
      "program": "${file}",
      "console": "integratedTerminal"
    }
  ]
}
```

### PyCharm

```python
# PyCharm configuration
# 1. Open project in PyCharm
# 2. Configure Python interpreter:
#    - File → Settings → Project → Python Interpreter
#    - Add interpreter → Virtualenv Environment → Existing environment
#    - Select: <project>/venv/bin/python

# 3. Configure code style:
#    - File → Settings → Editor → Code Style → Python
#    - Set to PEP 8, line length 100

# 4. Enable pytest:
#    - File → Settings → Tools → Python Integrated Tools
#    - Default test runner: pytest

# 5. Configure run configurations:
#    - Run → Edit Configurations
#    - Add FastAPI configuration (uvicorn app.main:app --reload)
```

---

## Running Services

### Docker Compose (Databases and Services)

```bash
# Start all services
docker compose up -d

# Start specific services
docker compose up -d postgres redis minio

# Check service status
docker compose ps

# View logs
docker compose logs -f postgres
docker compose logs -f redis

# Stop services
docker compose stop

# Stop and remove containers
docker compose down

# Stop and remove volumes (WARNING: deletes data!)
docker compose down -v
```

#### Docker Compose File

```yaml
# docker-compose.yml (Development)
version: '3.9'

services:
  postgres:
    image: postgres:16-alpine
    container_name: ablage-postgres-dev
    environment:
      POSTGRES_DB: ablage
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: password
      PGDATA: /var/lib/postgresql/data/pgdata
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: ablage-redis-dev
    command: redis-server --requirepass password --maxmemory 256mb --maxmemory-policy allkeys-lru
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "--raw", "incr", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5

  minio:
    image: minio/minio:latest
    container_name: ablage-minio-dev
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    ports:
      - "9000:9000"  # API
      - "9001:9001"  # Console
    volumes:
      - minio_data:/data
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 30s
      timeout: 20s
      retries: 3

volumes:
  postgres_data:
  redis_data:
  minio_data:
```

### Backend API

```bash
# Run with hot reload (development)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run with multiple workers (production-like)
uvicorn app.main:app --workers 4 --host 0.0.0.0 --port 8000

# Run with debugger
python -m debugpy --listen 0.0.0.0:5678 -m uvicorn app.main:app --reload

# Check API is running
curl http://localhost:8000/health

# Access interactive API docs
open http://localhost:8000/docs  # Swagger UI
open http://localhost:8000/redoc  # ReDoc
```

### Celery Worker

```bash
# Run worker (CPU only)
celery -A app.celery worker --loglevel=info --concurrency=4 --pool=prefork

# Run worker (GPU, single process)
celery -A app.celery worker --loglevel=debug --concurrency=1 --pool=solo

# Run with auto-reload (development)
watchmedo auto-restart \
  --directory=./app \
  --pattern='*.py' \
  --recursive \
  -- celery -A app.celery worker --loglevel=debug --concurrency=1 --pool=solo

# Monitor tasks (Flower)
pip install flower
celery -A app.celery flower --port=5555
# Open http://localhost:5555
```

### Frontend

```bash
# Navigate to frontend directory
cd frontend

# Run dev server with hot reload
npm run dev

# Run with specific port
npm run dev -- --port 3000

# Build for production (test)
npm run build

# Preview production build
npm run preview

# Access frontend
open http://localhost:3000
```

---

## Database Setup

### Initialize Database

```bash
# Create database (if not exists)
docker exec -it ablage-postgres-dev psql -U postgres -c "CREATE DATABASE ablage;"

# Create extensions
docker exec -it ablage-postgres-dev psql -U postgres -d ablage -c "CREATE EXTENSION IF NOT EXISTS pgvector;"
docker exec -it ablage-postgres-dev psql -U postgres -d ablage -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"

# Run migrations (create tables)
alembic upgrade head

# Check migration status
alembic current

# Check migration history
alembic history
```

### Create Sample Data

```bash
# Run seed script
python scripts/seed_data.py

# Or manually with psql
docker exec -it ablage-postgres-dev psql -U postgres -d ablage
```

```sql
-- Create test user
INSERT INTO users (id, email, username, password_hash, role, is_active)
VALUES (
  gen_random_uuid(),
  'test@example.com',
  'testuser',
  '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY0h1XKLHuGw0Ca',  -- password: password123
  'user',
  true
);

-- Create test document
INSERT INTO documents (id, owner_id, filename, file_size, status, created_at)
SELECT
  gen_random_uuid(),
  id,
  'test_document.pdf',
  1024000,
  'completed',
  NOW()
FROM users WHERE email = 'test@example.com';
```

### Database Utilities

```bash
# Connect to database
docker exec -it ablage-postgres-dev psql -U postgres -d ablage

# Backup database
docker exec ablage-postgres-dev pg_dump -U postgres ablage > backup.sql

# Restore database
docker exec -i ablage-postgres-dev psql -U postgres -d ablage < backup.sql

# Reset database (WARNING: deletes all data!)
alembic downgrade base
alembic upgrade head
python scripts/seed_data.py

# Show tables
docker exec -it ablage-postgres-dev psql -U postgres -d ablage -c "\dt"

# Show table schema
docker exec -it ablage-postgres-dev psql -U postgres -d ablage -c "\d documents"
```

---

## Running Tests

### Backend Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html --cov-report=term

# Run specific test file
pytest tests/test_documents.py

# Run specific test function
pytest tests/test_documents.py::test_create_document

# Run tests matching pattern
pytest -k "document"

# Run with verbose output
pytest -v

# Run with stdout (print statements visible)
pytest -s

# Run in parallel (faster)
pytest -n auto

# Watch mode (re-run on file changes)
ptw  # requires pytest-watch

# Generate HTML coverage report
pytest --cov=app --cov-report=html
open htmlcov/index.html
```

### Frontend Tests

```bash
cd frontend

# Run unit tests
npm run test:unit

# Run unit tests in watch mode
npm run test:unit -- --watch

# Run E2E tests (requires backend running)
npm run test:e2e

# Run E2E tests in headless mode
npm run test:e2e:headless

# Generate coverage report
npm run test:unit -- --coverage
```

### Integration Tests

```bash
# Run integration tests (requires services running)
pytest tests/integration/ -v

# Run with Docker Compose
docker compose -f docker-compose.test.yml up --abort-on-container-exit
```

---

## Debugging

### Backend Debugging

#### Using debugpy (VS Code)

```python
# Add to app/main.py (for debugging)
import debugpy

# Wait for debugger to attach
debugpy.listen(("0.0.0.0", 5678))
print("Waiting for debugger to attach...")
debugpy.wait_for_client()
print("Debugger attached!")

# Your code here
```

```bash
# Run with debugger
python -m debugpy --listen 0.0.0.0:5678 --wait-for-client -m uvicorn app.main:app --reload

# In VS Code: F5 to attach debugger
```

#### Using pdb (Python Debugger)

```python
# Add breakpoint in code
import pdb; pdb.set_trace()

# Or use built-in breakpoint() (Python 3.7+)
breakpoint()

# Debug commands:
# n - next line
# s - step into function
# c - continue
# l - list code
# p variable - print variable
# q - quit
```

### Frontend Debugging

#### Browser DevTools

```bash
# Run dev server
npm run dev

# Open in browser: http://localhost:3000
# Press F12 to open DevTools

# Vue DevTools extension:
# Chrome: https://chrome.google.com/webstore/detail/vuejs-devtools/
# Firefox: https://addons.mozilla.org/en-US/firefox/addon/vue-js-devtools/
```

#### VS Code Debugging

```json
// .vscode/launch.json (add to configurations)
{
  "name": "Vue: Chrome",
  "type": "chrome",
  "request": "launch",
  "url": "http://localhost:3000",
  "webRoot": "${workspaceFolder}/frontend/src",
  "sourceMapPathOverrides": {
    "webpack:///src/*": "${webRoot}/*"
  }
}
```

---

## Common Issues

### Issue: Port Already in Use

```bash
# Find process using port 8000
lsof -i :8000  # macOS/Linux
netstat -ano | findstr :8000  # Windows

# Kill process
kill -9 <PID>  # macOS/Linux
taskkill /PID <PID> /F  # Windows

# Or use different port
uvicorn app.main:app --reload --port 8001
```

### Issue: Database Connection Failed

```bash
# Check if PostgreSQL is running
docker compose ps postgres

# Check logs
docker compose logs postgres

# Restart PostgreSQL
docker compose restart postgres

# Verify connection manually
docker exec -it ablage-postgres-dev psql -U postgres -d ablage -c "SELECT 1;"

# Check DATABASE_URL in .env
echo $DATABASE_URL
```

### Issue: GPU Not Detected

```bash
# Check NVIDIA driver
nvidia-smi

# Check CUDA availability
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"

# Check Docker GPU support
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi

# If not working, reinstall nvidia-docker2
sudo apt-get install -y nvidia-docker2
sudo systemctl restart docker
```

### Issue: Import Errors

```bash
# Verify virtual environment is activated
which python  # Should show venv path

# Reinstall dependencies
pip install -r requirements.txt --force-reinstall

# Clear pip cache
pip cache purge

# Verify package installation
pip show fastapi
pip show sqlalchemy
```

### Issue: Frontend Build Fails

```bash
# Clear node_modules and reinstall
rm -rf node_modules package-lock.json
npm install

# Clear Vite cache
rm -rf frontend/.vite

# Check Node version
node --version  # Should be 20.x+

# Try with legacy peer deps
npm install --legacy-peer-deps
```

---

## Development Workflow

### Daily Workflow

```bash
# 1. Pull latest changes
git pull origin main

# 2. Activate virtual environment
source venv/bin/activate

# 3. Update dependencies (if needed)
pip install -r requirements.txt
cd frontend && npm install && cd ..

# 4. Start services
docker compose up -d

# 5. Run migrations (if new)
alembic upgrade head

# 6. Start backend
uvicorn app.main:app --reload

# 7. In another terminal, start frontend
cd frontend && npm run dev

# 8. Start coding!
```

### Creating a New Feature

```bash
# 1. Create feature branch
git checkout -b feature/my-new-feature

# 2. Make changes
# - Edit code
# - Write tests
# - Update documentation

# 3. Run tests
pytest
cd frontend && npm run test:unit

# 4. Lint and format
ruff check . --fix
ruff format .
cd frontend && npm run lint

# 5. Commit changes (pre-commit hooks will run)
git add .
git commit -m "feat: add my new feature"

# 6. Push to remote
git push origin feature/my-new-feature

# 7. Create pull request on GitHub
```

### Testing a Pull Request

```bash
# 1. Fetch PR
git fetch origin pull/123/head:pr-123
git checkout pr-123

# 2. Install dependencies (if changed)
pip install -r requirements.txt
cd frontend && npm install

# 3. Run migrations (if changed)
alembic upgrade head

# 4. Run tests
pytest
cd frontend && npm run test:unit

# 5. Manual testing
uvicorn app.main:app --reload
cd frontend && npm run dev

# 6. Leave review comments on GitHub
```

---

## Useful Commands

### Database

```bash
# Show all tables
docker exec -it ablage-postgres-dev psql -U postgres -d ablage -c "\dt"

# Show table structure
docker exec -it ablage-postgres-dev psql -U postgres -d ablage -c "\d documents"

# Count records
docker exec -it ablage-postgres-dev psql -U postgres -d ablage -c "SELECT COUNT(*) FROM documents;"

# Show recent documents
docker exec -it ablage-postgres-dev psql -U postgres -d ablage -c "SELECT id, filename, status, created_at FROM documents ORDER BY created_at DESC LIMIT 10;"
```

### Redis

```bash
# Connect to Redis
docker exec -it ablage-redis-dev redis-cli -a password

# Show all keys
KEYS *

# Get key value
GET key_name

# Delete key
DEL key_name

# Flush all data (WARNING!)
FLUSHALL
```

### MinIO

```bash
# Access MinIO console
open http://localhost:9001
# Login: minioadmin / minioadmin

# List buckets (using mc client)
docker run --rm --network host minio/mc alias set local http://localhost:9000 minioadmin minioadmin
docker run --rm --network host minio/mc ls local

# Create bucket
docker run --rm --network host minio/mc mb local/documents
```

### Logs

```bash
# View backend logs
tail -f logs/app.log

# View Docker logs
docker compose logs -f backend
docker compose logs -f worker

# View specific lines
docker compose logs --tail=100 backend
```

### Code Quality

```bash
# Run linter
ruff check .

# Auto-fix linting issues
ruff check . --fix

# Format code
ruff format .

# Type checking
mypy app/

# Security check
bandit -r app/

# Count lines of code
cloc app/ tests/
```

---

## Summary

You now have a complete local development environment for the Ablage-System!

**Quick Commands:**
```bash
# Start everything
docker compose up -d && uvicorn app.main:app --reload

# Run tests
pytest --cov=app

# Frontend dev
cd frontend && npm run dev
```

**Key Endpoints:**
- Frontend: http://localhost:3000
- API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- MinIO Console: http://localhost:9001
- Flower (Celery): http://localhost:5555

**Next Steps:**
- Review [Coding Conventions](../CONVENTIONS.md)
- Check [API Documentation](../API/api_client_examples.md)
- Read [Testing Guide](../Testing/testing_strategy.md)
- Join team chat for questions

Happy coding! 🚀

---

**Document Status:** ✅ **COMPLETE**
**Lines:** ~1,200
**Coverage:** Complete local development setup from installation to daily workflow with troubleshooting