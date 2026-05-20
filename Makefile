# Ablage-System Makefile
# Common development and deployment commands

.PHONY: help install dev test clean docker-build docker-up docker-down deploy

# Variables
PYTHON := python3.11
PIP := $(PYTHON) -m pip
DOCKER_COMPOSE := docker-compose
PROJECT_NAME := ablage-system

# Colors for output
RED := \033[0;31m
GREEN := \033[0;32m
YELLOW := \033[1;33m
NC := \033[0m # No Color

# Default target
help: ## Show this help message
	@echo "$(GREEN)Ablage-System - Available Commands$(NC)"
	@echo "======================================"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "$(YELLOW)%-20s$(NC) %s\n", $$1, $$2}'

# Development Setup
dev-setup: ## One-command developer onboarding (setup + build + migrate)
	@echo "$(YELLOW)Starting developer onboarding...$(NC)"
	@if [ ! -f .env ]; then \
		echo "$(YELLOW)Creating .env from .env.example...$(NC)"; \
		cp .env.example .env; \
		echo "$(RED)⚠ WICHTIG: Setze die PFLICHT-Variablen in .env!$(NC)"; \
		echo "$(YELLOW)Siehe .env fuer Details zu DB_PASSWORD, MINIO_*, SECRET_KEY, etc.$(NC)"; \
	else \
		echo "$(GREEN)✓ .env already exists$(NC)"; \
	fi
	@echo "$(YELLOW)Building Docker images...$(NC)"
	$(DOCKER_COMPOSE) build
	@echo "$(YELLOW)Starting services...$(NC)"
	$(DOCKER_COMPOSE) up -d
	@echo "$(YELLOW)Waiting for services to be healthy (30s)...$(NC)"
	@sleep 30
	@echo "$(YELLOW)Running database migrations...$(NC)"
	$(MAKE) db-migrate
	@echo ""
	@echo "$(GREEN)✓ Developer onboarding complete!$(NC)"
	@echo ""
	@echo "$(GREEN)Available URLs:$(NC)"
	@echo "  Web Interface: http://localhost"
	@echo "  API Docs: http://localhost:8000/docs"
	@echo "  Grafana: http://localhost:3002"
	@echo "  Flower: http://localhost:5555"
	@echo ""
	@echo "$(YELLOW)Next steps:$(NC)"
	@echo "  1. Configure .env with secure credentials"
	@echo "  2. Run 'make db-seed' to add test data"
	@echo "  3. Run 'make test' to verify setup"

install: ## Install development dependencies
	$(PIP) install --upgrade pip setuptools wheel
	$(PIP) install -r requirements.txt
	$(PIP) install -r requirements-dev.txt
	pre-commit install
	@echo "$(GREEN)✓ Development environment ready!$(NC)"

venv: ## Create virtual environment
	$(PYTHON) -m venv venv
	@echo "$(GREEN)✓ Virtual environment created. Activate with: source venv/bin/activate$(NC)"

dev: ## Run development server with hot reload
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Testing
test: ## Run all tests
	pytest -v

test-unit: ## Run unit tests only
	pytest -v -m unit

test-integration: ## Run integration tests
	pytest -v -m integration

test-cov: ## Run tests with coverage report
	pytest --cov=app --cov-report=html --cov-report=term

coverage: test-cov ## Alias for test-cov (generate coverage report)

test-gpu: ## Run GPU-specific tests
	pytest -v -m gpu

# Code Quality
lint: ## Run linting checks
	ruff check .

format: ## Format code with ruff
	ruff format .

type-check: ## Run type checking with mypy
	mypy app/ --strict

quality: lint format type-check ## Run all code quality checks

# Docker Commands
docker-build: ## Build Docker images
	$(DOCKER_COMPOSE) build

docker-up: ## Start all services with Docker Compose
	$(DOCKER_COMPOSE) up -d
	@echo "$(GREEN)✓ Services started!$(NC)"
	@echo "Web Interface: http://localhost"
	@echo "API Docs: http://localhost:8000/docs"

docker-down: ## Stop all Docker services
	$(DOCKER_COMPOSE) down

docker-logs: ## Show Docker logs
	$(DOCKER_COMPOSE) logs -f

docker-clean: ## Remove all containers and volumes
	$(DOCKER_COMPOSE) down -v
	docker system prune -f
	@echo "$(YELLOW)⚠ All containers and volumes removed$(NC)"

# Database
db-migrate: ## Run database migrations
	$(DOCKER_COMPOSE) run --rm backend alembic upgrade head

db-rollback: ## Rollback last migration
	$(DOCKER_COMPOSE) run --rm backend alembic downgrade -1

db-reset: ## Reset database (WARNING: destroys all data)
	$(DOCKER_COMPOSE) run --rm backend alembic downgrade base
	$(DOCKER_COMPOSE) run --rm backend alembic upgrade head
	@echo "$(YELLOW)⚠ Database reset complete$(NC)"

db-seed: ## Seed database with test data
	@echo "$(YELLOW)Seeding database with test data...$(NC)"
	$(DOCKER_COMPOSE) exec backend python -m scripts.seed_db
	@echo "$(GREEN)✓ Database seeded successfully!$(NC)"

# Production
deploy: ## Deploy to production
	@echo "$(YELLOW)Starting production deployment...$(NC)"
	./startup.sh start
	$(MAKE) db-migrate
	@echo "$(GREEN)✓ Deployment complete!$(NC)"

backup: ## Create backup of database and documents
	mkdir -p backups
	$(DOCKER_COMPOSE) exec postgres pg_dump -U ablage_admin ablage_system > backups/db_$(shell date +%Y%m%d_%H%M%S).sql
	$(DOCKER_COMPOSE) run --rm minio mc mirror local/documents backups/documents_$(shell date +%Y%m%d_%H%M%S)
	@echo "$(GREEN)✓ Backup complete!$(NC)"

# Monitoring
monitor: ## Open monitoring dashboards
	@echo "Opening monitoring tools..."
	@echo "Flower: http://localhost:5555"
	@echo "pgAdmin: http://localhost:5050"
	@echo "MinIO: http://localhost:9001"

logs: ## Show application logs
	$(DOCKER_COMPOSE) logs -f backend worker

metrics: ## Show system metrics
	curl -s http://localhost:8000/stats | python -m json.tool

health: ## Check system health
	@echo "Checking system health..."
	@curl -s http://localhost:8000/health | python -m json.tool

# Utilities
clean: ## Clean temporary files and caches
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name ".coverage" -delete
	rm -rf .pytest_cache
	rm -rf htmlcov
	rm -rf .mypy_cache
	rm -rf .ruff_cache
	@echo "$(GREEN)✓ Cleanup complete!$(NC)"

shell: ## Open shell in backend container
	$(DOCKER_COMPOSE) exec backend /bin/bash

psql: ## Open PostgreSQL shell
	$(DOCKER_COMPOSE) exec postgres psql -U ablage_admin -d ablage_system

redis-cli: ## Open Redis CLI
	$(DOCKER_COMPOSE) exec redis redis-cli

# Development Workflow
pr-check: quality test ## Run checks before creating PR
	@echo "$(GREEN)✓ All checks passed! Ready for PR.$(NC)"

setup: venv install docker-build ## Complete development setup
	@echo "$(GREEN)✓ Development environment fully configured!$(NC)"

restart: docker-down docker-up ## Restart all services
	@echo "$(GREEN)✓ Services restarted!$(NC)"

# GPU Management
gpu-status: ## Check GPU status
	nvidia-smi

gpu-test: ## Test GPU availability
	@$(PYTHON) -c "import torch; print('GPU Available:', torch.cuda.is_available()); print('GPU Name:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A')"

# Documentation
docs: ## Generate API documentation
	@echo "API documentation available at: http://localhost:8000/docs"

# Release Management
version: ## Show current version
	@grep "APP_VERSION" app/core/config.py | cut -d'"' -f2

release: pr-check ## Prepare for release
	@echo "$(YELLOW)Preparing release...$(NC)"
	@echo "1. Update version in app/core/config.py"
	@echo "2. Update CHANGELOG.md"
	@echo "3. Create git tag"
	@echo "4. Push to repository"

# Ansible Deployment
ansible-deps: ## Install Ansible Galaxy dependencies
	cd infrastructure/ansible && ansible-galaxy install -r requirements.yml
	@echo "$(GREEN)✓ Ansible dependencies installed!$(NC)"

ansible-check: ## Test Ansible connectivity to servers
	cd infrastructure/ansible && ansible -i inventories/production -m ping all

deploy-full: ## Full deployment with Ansible (site.yml)
	@echo "$(YELLOW)Starting full Ansible deployment...$(NC)"
	cd infrastructure/ansible && ansible-playbook -i inventories/production playbooks/site.yml
	@echo "$(GREEN)✓ Full deployment complete!$(NC)"

deploy-staging: ## Deploy to staging environment
	cd infrastructure/ansible && ansible-playbook -i inventories/staging playbooks/site.yml

deploy-app: ## Deploy application only (no provisioning)
	cd infrastructure/ansible && ansible-playbook -i inventories/production playbooks/deploy.yml

rolling-update: ## Zero-downtime rolling update
	@echo "$(YELLOW)Starting rolling update...$(NC)"
	cd infrastructure/ansible && ansible-playbook -i inventories/production playbooks/rolling-update.yml
	@echo "$(GREEN)✓ Rolling update complete!$(NC)"

ansible-backup: ## Create backup via Ansible
	cd infrastructure/ansible && ansible-playbook -i inventories/production playbooks/backup.yml

ansible-restore: ## Restore from backup (requires BACKUP_DATE)
	@if [ -z "$(BACKUP_DATE)" ]; then \
		echo "$(RED)Error: BACKUP_DATE not specified$(NC)"; \
		echo "Usage: make ansible-restore BACKUP_DATE=20241127"; \
		exit 1; \
	fi
	cd infrastructure/ansible && ansible-playbook -i inventories/production playbooks/restore.yml -e "backup_date=$(BACKUP_DATE)" -e "confirm_restore=true"

monitoring-setup: ## Setup monitoring stack via Ansible
	cd infrastructure/ansible && ansible-playbook -i inventories/production playbooks/monitoring-setup.yml

maintenance: ## Run system maintenance via Ansible
	cd infrastructure/ansible && ansible-playbook -i inventories/production playbooks/maintenance.yml

health-full: ## Full health check via Ansible
	cd infrastructure/ansible && ansible-playbook -i inventories/production playbooks/health-check.yml

ssl-setup: ## Setup SSL certificates via Ansible
	cd infrastructure/ansible && ansible-playbook -i inventories/production playbooks/ssl-setup.yml

.DEFAULT_GOAL := help
