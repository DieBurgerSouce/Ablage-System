# Ablage-System OCR - Makefile
# Central command hub for all operations
# Usage: make <target>

.PHONY: help setup dev prod test lint clean docker backup docs

# Variables
PYTHON := python3.11
PIP := pip
DOCKER_COMPOSE := docker-compose
DOCKER_COMPOSE_DEV := docker-compose -f docker-compose.yml -f docker-compose.dev.yml
PROJECT_NAME := ablage-system
TIMESTAMP := $(shell date +%Y%m%d_%H%M%S)

# Colors for output
RED := \033[0;31m
GREEN := \033[0;32m
YELLOW := \033[1;33m
BLUE := \033[0;34m
NC := \033[0m # No Color

##@ General

help: ## Show this help message
	@echo '$(BLUE)Ablage-System OCR - Available Commands$(NC)'
	@echo ''
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make $(YELLOW)<target>$(NC)\n"} /^[a-zA-Z_0-9-]+:.*?##/ { printf "  $(GREEN)%-20s$(NC) %s\n", $$1, $$2 } /^##@/ { printf "\n$(BLUE)%s$(NC)\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ Development Setup

setup: ## Complete initial setup (venv, dependencies, hooks, db)
	@echo "$(BLUE)🚀 Setting up Ablage-System...$(NC)"
	@echo "$(YELLOW)1/6 Creating virtual environment...$(NC)"
	$(PYTHON) -m venv venv
	@echo "$(YELLOW)2/6 Installing Python dependencies...$(NC)"
	. venv/bin/activate && $(PIP) install --upgrade pip
	. venv/bin/activate && $(PIP) install -r requirements.txt
	. venv/bin/activate && $(PIP) install -r requirements-dev.txt
	@echo "$(YELLOW)3/6 Setting up pre-commit hooks...$(NC)"
	. venv/bin/activate && pre-commit install --install-hooks
	. venv/bin/activate && pre-commit install --hook-type commit-msg
	@echo "$(YELLOW)4/6 Creating .env file from template...$(NC)"
	@if [ ! -f .env ]; then cp .env.example .env; fi
	@echo "$(YELLOW)5/6 Starting Docker services...$(NC)"
	$(DOCKER_COMPOSE_DEV) up -d postgres redis minio
	@sleep 5
	@echo "$(YELLOW)6/6 Running database migrations...$(NC)"
	. venv/bin/activate && alembic upgrade head || echo "$(RED)Migrations failed - run manually$(NC)"
	@echo "$(GREEN)✅ Setup complete!$(NC)"
	@echo "$(BLUE)Next steps:$(NC)"
	@echo "  1. Review and update .env file"
	@echo "  2. Run: make dev"
	@echo "  3. Visit: http://localhost:8000/docs"

install: ## Install Python dependencies only
	@echo "$(BLUE)📦 Installing dependencies...$(NC)"
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	$(PIP) install -r requirements-dev.txt
	@echo "$(GREEN)✅ Dependencies installed$(NC)"

update: ## Update all dependencies to latest versions
	@echo "$(BLUE)🔄 Updating dependencies...$(NC)"
	$(PIP) install --upgrade pip
	$(PIP) install --upgrade -r requirements.txt
	$(PIP) install --upgrade -r requirements-dev.txt
	$(PIP) freeze > requirements-updated.txt
	@echo "$(GREEN)✅ Dependencies updated$(NC)"
	@echo "$(YELLOW)Review requirements-updated.txt and update requirements.txt if needed$(NC)"

hooks: ## Setup Git pre-commit hooks
	@echo "$(BLUE)🪝 Setting up Git hooks...$(NC)"
	pre-commit install --install-hooks
	pre-commit install --hook-type commit-msg
	@echo "$(GREEN)✅ Hooks installed$(NC)"

##@ Development

dev: ## Start development environment (all services with hot reload)
	@echo "$(BLUE)🚀 Starting development environment...$(NC)"
	$(DOCKER_COMPOSE_DEV) up -d
	@echo "$(GREEN)✅ Development environment running$(NC)"
	@echo "$(BLUE)Services:$(NC)"
	@echo "  API:              http://localhost:8000"
	@echo "  API Docs:         http://localhost:8000/docs"
	@echo "  pgAdmin:          http://localhost:5050"
	@echo "  Redis Commander:  http://localhost:8081"
	@echo "  MinIO Console:    http://localhost:9001"
	@echo "  Flower:           http://localhost:5555"

dev-build: ## Rebuild and start development environment
	@echo "$(BLUE)🔨 Rebuilding development environment...$(NC)"
	$(DOCKER_COMPOSE_DEV) up -d --build
	@echo "$(GREEN)✅ Development environment rebuilt and running$(NC)"

dev-down: ## Stop development environment
	@echo "$(BLUE)🛑 Stopping development environment...$(NC)"
	$(DOCKER_COMPOSE_DEV) down
	@echo "$(GREEN)✅ Development environment stopped$(NC)"

dev-restart: ## Restart development environment
	@echo "$(BLUE)🔄 Restarting development environment...$(NC)"
	$(DOCKER_COMPOSE_DEV) restart
	@echo "$(GREEN)✅ Development environment restarted$(NC)"

shell-backend: ## Open shell in backend container
	@echo "$(BLUE)🐚 Opening backend shell...$(NC)"
	$(DOCKER_COMPOSE_DEV) exec backend /bin/bash

shell-worker: ## Open shell in worker container
	@echo "$(BLUE)🐚 Opening worker shell...$(NC)"
	$(DOCKER_COMPOSE_DEV) exec worker /bin/bash

shell-redis: ## Open Redis CLI
	@echo "$(BLUE)🐚 Opening Redis CLI...$(NC)"
	$(DOCKER_COMPOSE_DEV) exec redis redis-cli

##@ Production

prod: ## Start production environment
	@echo "$(BLUE)🚀 Starting production environment...$(NC)"
	$(DOCKER_COMPOSE) up -d
	@echo "$(GREEN)✅ Production environment running$(NC)"

prod-build: ## Build production images and start
	@echo "$(BLUE)🔨 Building production environment...$(NC)"
	$(DOCKER_COMPOSE) up -d --build
	@echo "$(GREEN)✅ Production environment built and running$(NC)"

prod-down: ## Stop production environment
	@echo "$(BLUE)🛑 Stopping production environment...$(NC)"
	$(DOCKER_COMPOSE) down
	@echo "$(GREEN)✅ Production environment stopped$(NC)"

##@ Testing

test: ## Run all tests
	@echo "$(BLUE)🧪 Running all tests...$(NC)"
	pytest tests/ -v
	@echo "$(GREEN)✅ Tests complete$(NC)"

test-cov: ## Run tests with coverage report
	@echo "$(BLUE)🧪 Running tests with coverage...$(NC)"
	pytest tests/ -v --cov=app --cov-report=html --cov-report=term
	@echo "$(GREEN)✅ Tests complete with coverage$(NC)"
	@echo "$(BLUE)Coverage report: htmlcov/index.html$(NC)"

test-unit: ## Run unit tests only
	@echo "$(BLUE)🧪 Running unit tests...$(NC)"
	pytest tests/unit/ -v
	@echo "$(GREEN)✅ Unit tests complete$(NC)"

test-integration: ## Run integration tests only
	@echo "$(BLUE)🧪 Running integration tests...$(NC)"
	pytest tests/integration/ -v
	@echo "$(GREEN)✅ Integration tests complete$(NC)"

test-gpu: ## Run GPU tests only
	@echo "$(BLUE)🧪 Running GPU tests...$(NC)"
	pytest tests/ -v -m gpu
	@echo "$(GREEN)✅ GPU tests complete$(NC)"

test-watch: ## Run tests in watch mode (auto-rerun on changes)
	@echo "$(BLUE)🧪 Running tests in watch mode...$(NC)"
	pytest-watch tests/ -v

test-parallel: ## Run tests in parallel (faster)
	@echo "$(BLUE)🧪 Running tests in parallel...$(NC)"
	pytest tests/ -v -n auto
	@echo "$(GREEN)✅ Parallel tests complete$(NC)"

##@ Code Quality

lint: ## Run all linters (Ruff, MyPy)
	@echo "$(BLUE)🔍 Running linters...$(NC)"
	@echo "$(YELLOW)Ruff...$(NC)"
	ruff check .
	@echo "$(YELLOW)MyPy...$(NC)"
	mypy app/
	@echo "$(GREEN)✅ Linting complete$(NC)"

lint-fix: ## Run linters with auto-fix
	@echo "$(BLUE)🔧 Running linters with auto-fix...$(NC)"
	ruff check . --fix
	@echo "$(GREEN)✅ Linting complete with fixes$(NC)"

format: ## Format code with Ruff
	@echo "$(BLUE)✨ Formatting code...$(NC)"
	ruff format .
	@echo "$(GREEN)✅ Code formatted$(NC)"

format-check: ## Check code formatting without changes
	@echo "$(BLUE)🔍 Checking code formatting...$(NC)"
	ruff format --check .
	@echo "$(GREEN)✅ Format check complete$(NC)"

type-check: ## Run type checking with MyPy
	@echo "$(BLUE)🔍 Running type checking...$(NC)"
	mypy app/ --strict
	@echo "$(GREEN)✅ Type checking complete$(NC)"

security-scan: ## Run security scans (Bandit, Safety)
	@echo "$(BLUE)🔒 Running security scans...$(NC)"
	@echo "$(YELLOW)Bandit...$(NC)"
	bandit -r app/ -f screen
	@echo "$(YELLOW)Safety...$(NC)"
	safety check --json || echo "$(YELLOW)Safety check completed with warnings$(NC)"
	@echo "$(GREEN)✅ Security scans complete$(NC)"

pre-commit: ## Run pre-commit hooks on all files
	@echo "$(BLUE)🪝 Running pre-commit hooks...$(NC)"
	pre-commit run --all-files
	@echo "$(GREEN)✅ Pre-commit checks complete$(NC)"

##@ Database

db-migrate: ## Run database migrations
	@echo "$(BLUE)🔄 Running database migrations...$(NC)"
	alembic upgrade head
	@echo "$(GREEN)✅ Migrations complete$(NC)"

db-migrate-create: ## Create new migration (MSG="description")
	@echo "$(BLUE)📝 Creating new migration...$(NC)"
	@if [ -z "$(MSG)" ]; then \
		echo "$(RED)❌ Error: MSG is required$(NC)"; \
		echo "Usage: make db-migrate-create MSG='description'"; \
		exit 1; \
	fi
	alembic revision --autogenerate -m "$(MSG)"
	@echo "$(GREEN)✅ Migration created$(NC)"

db-downgrade: ## Downgrade database by one revision
	@echo "$(BLUE)⬇️  Downgrading database...$(NC)"
	alembic downgrade -1
	@echo "$(GREEN)✅ Database downgraded$(NC)"

db-history: ## Show migration history
	@echo "$(BLUE)📜 Migration history:$(NC)"
	alembic history

db-current: ## Show current migration version
	@echo "$(BLUE)📍 Current migration:$(NC)"
	alembic current

db-shell: ## Open PostgreSQL shell
	@echo "$(BLUE)🐘 Opening PostgreSQL shell...$(NC)"
	$(DOCKER_COMPOSE_DEV) exec postgres psql -U postgres -d ablage_ocr

db-reset: ## Reset database (⚠️ DESTROYS ALL DATA!)
	@echo "$(RED)⚠️  WARNING: This will destroy all data!$(NC)"
	@read -p "Are you sure? Type 'yes' to continue: " confirm; \
	if [ "$$confirm" = "yes" ]; then \
		echo "$(BLUE)🔄 Resetting database...$(NC)"; \
		./scripts/db-reset.sh; \
		echo "$(GREEN)✅ Database reset complete$(NC)"; \
	else \
		echo "$(YELLOW)Cancelled$(NC)"; \
	fi

db-backup: ## Backup database to file
	@echo "$(BLUE)💾 Backing up database...$(NC)"
	./scripts/backup.sh db
	@echo "$(GREEN)✅ Database backup complete$(NC)"

db-seed: ## Seed database with test data
	@echo "$(BLUE)🌱 Seeding database...$(NC)"
	python scripts/seed_db.py
	@echo "$(GREEN)✅ Database seeded$(NC)"

##@ Docker

build: ## Build all Docker images
	@echo "$(BLUE)🔨 Building Docker images...$(NC)"
	$(DOCKER_COMPOSE) build
	@echo "$(GREEN)✅ Images built$(NC)"

build-backend: ## Build backend image only
	@echo "$(BLUE)🔨 Building backend image...$(NC)"
	$(DOCKER_COMPOSE) build backend
	@echo "$(GREEN)✅ Backend image built$(NC)"

build-worker: ## Build worker image only
	@echo "$(BLUE)🔨 Building worker image...$(NC)"
	$(DOCKER_COMPOSE) build worker
	@echo "$(GREEN)✅ Worker image built$(NC)"

pull: ## Pull latest base images
	@echo "$(BLUE)📥 Pulling latest base images...$(NC)"
	$(DOCKER_COMPOSE) pull
	@echo "$(GREEN)✅ Images pulled$(NC)"

ps: ## Show running containers
	@echo "$(BLUE)📊 Running containers:$(NC)"
	$(DOCKER_COMPOSE_DEV) ps

logs: ## Follow logs from all containers
	@echo "$(BLUE)📋 Following logs (Ctrl+C to stop)...$(NC)"
	$(DOCKER_COMPOSE_DEV) logs -f

logs-backend: ## Follow backend logs
	@echo "$(BLUE)📋 Following backend logs...$(NC)"
	$(DOCKER_COMPOSE_DEV) logs -f backend

logs-worker: ## Follow worker logs
	@echo "$(BLUE)📋 Following worker logs...$(NC)"
	$(DOCKER_COMPOSE_DEV) logs -f worker

logs-db: ## Follow database logs
	@echo "$(BLUE)📋 Following database logs...$(NC)"
	$(DOCKER_COMPOSE_DEV) logs -f postgres

health: ## Check health of all services
	@echo "$(BLUE)🏥 Checking service health...$(NC)"
	@$(DOCKER_COMPOSE_DEV) ps --format json | python -m json.tool
	@echo "$(GREEN)✅ Health check complete$(NC)"

##@ GPU

gpu-status: ## Check GPU status (nvidia-smi)
	@echo "$(BLUE)🎮 GPU Status:$(NC)"
	nvidia-smi

gpu-test: ## Test GPU availability in container
	@echo "$(BLUE)🧪 Testing GPU in container...$(NC)"
	$(DOCKER_COMPOSE_DEV) exec worker python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}'); print(f'GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"N/A\"}')"

gpu-logs: ## Monitor GPU in real-time
	@echo "$(BLUE)📊 Monitoring GPU (Ctrl+C to stop)...$(NC)"
	watch -n 1 nvidia-smi

##@ Cleanup

clean: ## Remove all containers, volumes, and cache
	@echo "$(RED)⚠️  This will remove all containers, volumes, and cache!$(NC)"
	@read -p "Are you sure? Type 'yes' to continue: " confirm; \
	if [ "$$confirm" = "yes" ]; then \
		echo "$(BLUE)🧹 Cleaning up...$(NC)"; \
		$(DOCKER_COMPOSE_DEV) down -v; \
		rm -rf __pycache__ .pytest_cache .mypy_cache .ruff_cache; \
		find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true; \
		find . -type f -name "*.pyc" -delete 2>/dev/null || true; \
		echo "$(GREEN)✅ Cleanup complete$(NC)"; \
	else \
		echo "$(YELLOW)Cancelled$(NC)"; \
	fi

clean-cache: ## Remove Python cache files
	@echo "$(BLUE)🧹 Removing Python cache...$(NC)"
	rm -rf __pycache__ .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "$(GREEN)✅ Cache cleaned$(NC)"

clean-volumes: ## Remove Docker volumes (⚠️ DATA LOSS!)
	@echo "$(RED)⚠️  This will remove all Docker volumes and DATA!$(NC)"
	@read -p "Are you sure? Type 'yes' to continue: " confirm; \
	if [ "$$confirm" = "yes" ]; then \
		echo "$(BLUE)🧹 Removing volumes...$(NC)"; \
		$(DOCKER_COMPOSE_DEV) down -v; \
		echo "$(GREEN)✅ Volumes removed$(NC)"; \
	else \
		echo "$(YELLOW)Cancelled$(NC)"; \
	fi

clean-docker: ## Remove all Docker images and containers
	@echo "$(RED)⚠️  This will remove all Docker images and containers!$(NC)"
	@read -p "Are you sure? Type 'yes' to continue: " confirm; \
	if [ "$$confirm" = "yes" ]; then \
		echo "$(BLUE)🧹 Cleaning Docker...$(NC)"; \
		docker system prune -af --volumes; \
		echo "$(GREEN)✅ Docker cleaned$(NC)"; \
	else \
		echo "$(YELLOW)Cancelled$(NC)"; \
	fi

##@ Backup & Restore

backup: ## Backup database and MinIO data
	@echo "$(BLUE)💾 Creating backup...$(NC)"
	./scripts/backup.sh all
	@echo "$(GREEN)✅ Backup complete: backups/backup_$(TIMESTAMP).tar.gz$(NC)"

backup-db: ## Backup database only
	@echo "$(BLUE)💾 Backing up database...$(NC)"
	./scripts/backup.sh db
	@echo "$(GREEN)✅ Database backup complete$(NC)"

backup-minio: ## Backup MinIO data only
	@echo "$(BLUE)💾 Backing up MinIO...$(NC)"
	./scripts/backup.sh minio
	@echo "$(GREEN)✅ MinIO backup complete$(NC)"

restore: ## Restore from backup (BACKUP=path/to/backup.tar.gz)
	@echo "$(BLUE)📥 Restoring from backup...$(NC)"
	@if [ -z "$(BACKUP)" ]; then \
		echo "$(RED)❌ Error: BACKUP path is required$(NC)"; \
		echo "Usage: make restore BACKUP=path/to/backup.tar.gz"; \
		exit 1; \
	fi
	./scripts/restore.sh $(BACKUP)
	@echo "$(GREEN)✅ Restore complete$(NC)"

##@ Monitoring & Observability

monitor: ## Start monitoring stack (Prometheus + Grafana)
	@echo "$(BLUE)📊 Starting monitoring stack...$(NC)"
	$(DOCKER_COMPOSE) --profile monitoring up -d
	@echo "$(GREEN)✅ Monitoring running$(NC)"
	@echo "$(BLUE)Services:$(NC)"
	@echo "  Prometheus: http://localhost:9090"
	@echo "  Grafana:    http://localhost:3000 (admin/admin)"

monitor-down: ## Stop monitoring stack
	@echo "$(BLUE)🛑 Stopping monitoring stack...$(NC)"
	$(DOCKER_COMPOSE) --profile monitoring down
	@echo "$(GREEN)✅ Monitoring stopped$(NC)"

##@ Documentation

docs: ## Build documentation site
	@echo "$(BLUE)📚 Building documentation...$(NC)"
	mkdocs build
	@echo "$(GREEN)✅ Documentation built: site/$(NC)"

docs-serve: ## Serve documentation locally
	@echo "$(BLUE)📚 Serving documentation...$(NC)"
	@echo "$(BLUE)Visit: http://localhost:8080$(NC)"
	mkdocs serve -a localhost:8080

docs-deploy: ## Deploy documentation to GitHub Pages
	@echo "$(BLUE)📚 Deploying documentation...$(NC)"
	mkdocs gh-deploy
	@echo "$(GREEN)✅ Documentation deployed$(NC)"

##@ Jupyter

jupyter: ## Start Jupyter Lab
	@echo "$(BLUE)📊 Starting Jupyter Lab...$(NC)"
	./scripts/start_jupyter.sh
	@echo "$(BLUE)Visit: http://localhost:8888$(NC)"

##@ Deployment

deploy-check: ## Run pre-deployment checks
	@echo "$(BLUE)🔍 Running deployment checks...$(NC)"
	@echo "$(YELLOW)This will take a few minutes...$(NC)"
	python scripts/deploy_check.py
	@echo "$(GREEN)✅ Deployment checks complete$(NC)"

deploy-staging: ## Deploy to staging environment
	@echo "$(BLUE)🚀 Deploying to staging...$(NC)"
	./scripts/deploy.sh staging
	@echo "$(GREEN)✅ Deployed to staging$(NC)"

deploy-prod: ## Deploy to production environment
	@echo "$(RED)⚠️  Deploying to production!$(NC)"
	@read -p "Are you sure? Type 'yes' to continue: " confirm; \
	if [ "$$confirm" = "yes" ]; then \
		echo "$(BLUE)🚀 Deploying to production...$(NC)"; \
		./scripts/deploy.sh production; \
		echo "$(GREEN)✅ Deployed to production$(NC)"; \
	else \
		echo "$(YELLOW)Cancelled$(NC)"; \
	fi

rollback: ## Rollback to previous version
	@echo "$(BLUE)⏮️  Rolling back...$(NC)"
	./scripts/rollback.sh
	@echo "$(GREEN)✅ Rollback complete$(NC)"

##@ Utilities

recreate: ## Recreate environment (down, build, up, migrate)
	@echo "$(BLUE)🔄 Recreating environment...$(NC)"
	$(DOCKER_COMPOSE_DEV) down
	$(DOCKER_COMPOSE_DEV) up -d --build
	@sleep 5
	alembic upgrade head
	@echo "$(GREEN)✅ Environment recreated$(NC)"

urls: ## Show all service URLs
	@echo "$(BLUE)🌐 Service URLs:$(NC)"
	@echo "  API:              http://localhost:8000"
	@echo "  API Docs:         http://localhost:8000/docs"
	@echo "  ReDoc:            http://localhost:8000/redoc"
	@echo "  pgAdmin:          http://localhost:5050"
	@echo "  Redis Commander:  http://localhost:8081"
	@echo "  MinIO Console:    http://localhost:9001"
	@echo "  Flower:           http://localhost:5555"
	@echo "  Prometheus:       http://localhost:9090"
	@echo "  Grafana:          http://localhost:3000"
	@echo "  Jupyter:          http://localhost:8888"

version: ## Show version information
	@echo "$(BLUE)Ablage-System OCR$(NC)"
	@echo "Version: $(shell cat VERSION 2>/dev/null || echo 'dev')"
	@echo "Python: $(shell $(PYTHON) --version)"
	@echo "Docker: $(shell docker --version)"
	@echo "Docker Compose: $(shell docker-compose --version)"

.DEFAULT_GOAL := help
