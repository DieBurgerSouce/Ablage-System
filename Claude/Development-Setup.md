DEVELOPMENT SETUP & ENVIRONMENT GUIDE - TEIL 1
Complete Guide to Development Environment Setup

📋 TABLE OF CONTENTS

Introduction
Local Environment Setup
IDE Configuration
Virtual Environment Setup


🎯 INTRODUCTION
Why Proper Development Setup Matters
┌─────────────────────────────────────────────────────────┐
│         DEVELOPMENT SETUP CHALLENGES                     │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  🔧 Consistency                                          │
│     - Same environment across team                       │
│     - Avoid "works on my machine"                        │
│     - Reproducible builds                                │
│                                                         │
│  🚀 Productivity                                         │
│     - Fast development cycles                            │
│     - Efficient debugging                                │
│     - Automated workflows                                │
│                                                         │
│  🐛 Quality                                              │
│     - Catch errors early                                 │
│     - Consistent code style                              │
│     - Automated testing                                  │
│                                                         │
│  👥 Collaboration                                        │
│     - Easy onboarding                                    │
│     - Shared configurations                              │
│     - Version control integration                        │
│                                                         │
└─────────────────────────────────────────────────────────┘
Development Environment Overview
┌──────────────────────────────────────────────────────────────┐
│              DEVELOPMENT ENVIRONMENT STACK                    │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  📦 System Requirements                                       │
│     - Python 3.11+                                           │
│     - PostgreSQL 16+                                         │
│     - Redis 7+                                               │
│     - Node.js 20+ (for frontend)                             │
│                                                              │
│  🔧 Development Tools                                         │
│     - IDE (VSCode/PyCharm)                                   │
│     - Git                                                    │
│     - Docker & Docker Compose                                │
│     - Make (task automation)                                 │
│                                                              │
│  🐍 Python Environment                                        │
│     - Virtual Environment (venv/pyenv)                       │
│     - Package Manager (pip/poetry)                           │
│     - Linting (ruff, black)                                  │
│     - Type Checking (mypy)                                   │
│                                                              │
│  🗄️ Database & Services                                       │
│     - PostgreSQL (local/Docker)                              │
│     - Redis (caching/queues)                                 │
│     - MinIO (S3-compatible storage)                          │
│     - ClamAV (virus scanning)                                │
│                                                              │
└──────────────────────────────────────────────────────────────┘

🖥️ LOCAL ENVIRONMENT SETUP
1. System Requirements Check
bash#!/bin/bash
# scripts/check_requirements.sh

# ============================================
# SYSTEM REQUIREMENTS CHECKER
# ============================================
#
# Checks if all required tools are installed
# and meets minimum version requirements
#
# Usage: ./check_requirements.sh
# ============================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Requirements
REQUIRED_PYTHON_VERSION="3.11"
REQUIRED_POSTGRES_VERSION="16"
REQUIRED_REDIS_VERSION="7"
REQUIRED_NODE_VERSION="20"
REQUIRED_DOCKER_VERSION="24"

# ============================================
# HELPER FUNCTIONS
# ============================================

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_header() {
    echo ""
    echo "=========================================="
    echo "$1"
    echo "=========================================="
}

version_compare() {
    # Compare version strings
    # Returns 0 if $1 >= $2
    printf '%s\n%s\n' "$2" "$1" | sort -V -C
}

# ============================================
# CHECK PYTHON
# ============================================

check_python() {
    print_header "Checking Python"
    
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
        echo "Found Python: $PYTHON_VERSION"
        
        if version_compare "$PYTHON_VERSION" "$REQUIRED_PYTHON_VERSION"; then
            print_success "Python version OK (>= $REQUIRED_PYTHON_VERSION)"
        else
            print_error "Python version too old. Required: >= $REQUIRED_PYTHON_VERSION"
            echo "Install from: https://www.python.org/downloads/"
            return 1
        fi
    else
        print_error "Python 3 not found"
        echo "Install from: https://www.python.org/downloads/"
        return 1
    fi
    
    # Check pip
    if command -v pip3 &> /dev/null; then
        print_success "pip3 found: $(pip3 --version)"
    else
        print_error "pip3 not found"
        return 1
    fi
}

# ============================================
# CHECK POSTGRESQL
# ============================================

check_postgresql() {
    print_header "Checking PostgreSQL"
    
    if command -v psql &> /dev/null; then
        POSTGRES_VERSION=$(psql --version | grep -oP '\d+' | head -1)
        echo "Found PostgreSQL: $POSTGRES_VERSION"
        
        if [ "$POSTGRES_VERSION" -ge "$REQUIRED_POSTGRES_VERSION" ]; then
            print_success "PostgreSQL version OK (>= $REQUIRED_POSTGRES_VERSION)"
        else
            print_warning "PostgreSQL version is older than recommended ($REQUIRED_POSTGRES_VERSION)"
        fi
    else
        print_warning "PostgreSQL not found (optional if using Docker)"
        echo "Install from: https://www.postgresql.org/download/"
    fi
}

# ============================================
# CHECK REDIS
# ============================================

check_redis() {
    print_header "Checking Redis"
    
    if command -v redis-cli &> /dev/null; then
        REDIS_VERSION=$(redis-cli --version | grep -oP '\d+\.\d+' | head -1)
        echo "Found Redis: $REDIS_VERSION"
        print_success "Redis found"
    else
        print_warning "Redis not found (optional if using Docker)"
        echo "Install from: https://redis.io/download"
    fi
}

# ============================================
# CHECK DOCKER
# ============================================

check_docker() {
    print_header "Checking Docker"
    
    if command -v docker &> /dev/null; then
        DOCKER_VERSION=$(docker --version | grep -oP '\d+\.\d+' | head -1)
        echo "Found Docker: $DOCKER_VERSION"
        
        if version_compare "$DOCKER_VERSION" "$REQUIRED_DOCKER_VERSION"; then
            print_success "Docker version OK (>= $REQUIRED_DOCKER_VERSION)"
        else
            print_warning "Docker version is older than recommended ($REQUIRED_DOCKER_VERSION)"
        fi
        
        # Check if Docker daemon is running
        if docker info &> /dev/null; then
            print_success "Docker daemon is running"
        else
            print_error "Docker daemon is not running"
            echo "Start Docker Desktop or run: sudo systemctl start docker"
            return 1
        fi
    else
        print_error "Docker not found"
        echo "Install from: https://docs.docker.com/get-docker/"
        return 1
    fi
    
    # Check Docker Compose
    if command -v docker-compose &> /dev/null; then
        print_success "Docker Compose found: $(docker-compose --version)"
    else
        print_warning "Docker Compose not found (using docker compose plugin)"
    fi
}

# ============================================
# CHECK NODE.JS (for frontend)
# ============================================

check_nodejs() {
    print_header "Checking Node.js (Optional)"
    
    if command -v node &> /dev/null; then
        NODE_VERSION=$(node --version | grep -oP '\d+' | head -1)
        echo "Found Node.js: v$(node --version)"
        
        if [ "$NODE_VERSION" -ge "$REQUIRED_NODE_VERSION" ]; then
            print_success "Node.js version OK (>= $REQUIRED_NODE_VERSION)"
        else
            print_warning "Node.js version is older than recommended ($REQUIRED_NODE_VERSION)"
        fi
        
        # Check npm
        if command -v npm &> /dev/null; then
            print_success "npm found: $(npm --version)"
        fi
    else
        print_warning "Node.js not found (optional for backend-only development)"
        echo "Install from: https://nodejs.org/"
    fi
}

# ============================================
# CHECK GIT
# ============================================

check_git() {
    print_header "Checking Git"
    
    if command -v git &> /dev/null; then
        GIT_VERSION=$(git --version | grep -oP '\d+\.\d+\.\d+')
        echo "Found Git: $GIT_VERSION"
        print_success "Git found"
        
        # Check Git configuration
        if git config user.name &> /dev/null && git config user.email &> /dev/null; then
            print_success "Git configured (name: $(git config user.name), email: $(git config user.email))"
        else
            print_warning "Git not configured. Run:"
            echo "  git config --global user.name 'Your Name'"
            echo "  git config --global user.email 'your.email@example.com'"
        fi
    else
        print_error "Git not found"
        echo "Install from: https://git-scm.com/downloads"
        return 1
    fi
}

# ============================================
# CHECK MAKE
# ============================================

check_make() {
    print_header "Checking Make"
    
    if command -v make &> /dev/null; then
        print_success "Make found: $(make --version | head -1)"
    else
        print_warning "Make not found (optional, used for task automation)"
        echo "Install: sudo apt install build-essential (Ubuntu/Debian)"
        echo "      or brew install make (macOS)"
    fi
}

# ============================================
# CHECK EDITOR
# ============================================

check_editor() {
    print_header "Checking Code Editor"
    
    FOUND_EDITOR=false
    
    # Check VS Code
    if command -v code &> /dev/null; then
        print_success "VS Code found"
        FOUND_EDITOR=true
    fi
    
    # Check PyCharm
    if command -v pycharm &> /dev/null || command -v charm &> /dev/null; then
        print_success "PyCharm found"
        FOUND_EDITOR=true
    fi
    
    if [ "$FOUND_EDITOR" = false ]; then
        print_warning "No code editor found"
        echo "Recommended: VS Code (https://code.visualstudio.com/)"
        echo "         or: PyCharm (https://www.jetbrains.com/pycharm/)"
    fi
}

# ============================================
# MAIN EXECUTION
# ============================================

main() {
    echo "╔════════════════════════════════════════╗"
    echo "║  DEVELOPMENT ENVIRONMENT CHECKER       ║"
    echo "╚════════════════════════════════════════╝"
    
    ERRORS=0
    
    check_python || ((ERRORS++))
    check_git || ((ERRORS++))
    check_docker || ((ERRORS++))
    check_postgresql
    check_redis
    check_nodejs
    check_make
    check_editor
    
    # Summary
    print_header "Summary"
    
    if [ $ERRORS -eq 0 ]; then
        print_success "All required dependencies are installed!"
        echo ""
        echo "Next steps:"
        echo "  1. Clone the repository"
        echo "  2. Run: make setup"
        echo "  3. Run: make dev"
        echo ""
        return 0
    else
        print_error "Found $ERRORS critical issue(s)"
        echo ""
        echo "Please install missing dependencies and try again."
        echo ""
        return 1
    fi
}

main
2. Project Setup Script
bash#!/bin/bash
# scripts/setup_dev_environment.sh

# ============================================
# DEVELOPMENT ENVIRONMENT SETUP
# ============================================
#
# Complete setup script for development
#
# Usage: ./setup_dev_environment.sh
# ============================================

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log() {
    echo -e "${BLUE}==>${NC} $1"
}

success() {
    echo -e "${GREEN}✓${NC} $1"
}

# ============================================
# SETUP PYTHON VIRTUAL ENVIRONMENT
# ============================================

setup_venv() {
    log "Setting up Python virtual environment"
    
    if [ ! -d "venv" ]; then
        python3 -m venv venv
        success "Virtual environment created"
    else
        log "Virtual environment already exists"
    fi
    
    # Activate virtual environment
    source venv/bin/activate
    
    # Upgrade pip
    log "Upgrading pip"
    pip install --upgrade pip
    
    success "Virtual environment ready"
}

# ============================================
# INSTALL PYTHON DEPENDENCIES
# ============================================

install_dependencies() {
    log "Installing Python dependencies"
    
    # Activate venv
    source venv/bin/activate
    
    # Install requirements
    if [ -f "requirements.txt" ]; then
        pip install -r requirements.txt
        success "Production dependencies installed"
    fi
    
    if [ -f "requirements-dev.txt" ]; then
        pip install -r requirements-dev.txt
        success "Development dependencies installed"
    fi
}

# ============================================
# SETUP PRE-COMMIT HOOKS
# ============================================

setup_precommit() {
    log "Setting up pre-commit hooks"
    
    source venv/bin/activate
    
    if command -v pre-commit &> /dev/null; then
        pre-commit install
        success "Pre-commit hooks installed"
    else
        log "pre-commit not found, skipping"
    fi
}

# ============================================
# SETUP ENVIRONMENT VARIABLES
# ============================================

setup_env() {
    log "Setting up environment variables"
    
    if [ ! -f ".env" ]; then
        if [ -f ".env.example" ]; then
            cp .env.example .env
            success "Created .env from .env.example"
            echo "⚠️  Please edit .env and configure your settings"
        else
            log "No .env.example found, skipping"
        fi
    else
        log ".env already exists"
    fi
}

# ============================================
# SETUP DOCKER SERVICES
# ============================================

setup_docker() {
    log "Setting up Docker services"
    
    if command -v docker &> /dev/null; then
        # Check if docker-compose.yml exists
        if [ -f "docker-compose.yml" ]; then
            log "Starting Docker services"
            docker-compose up -d postgres redis minio
            
            # Wait for services to be ready
            log "Waiting for services to be ready..."
            sleep 5
            
            success "Docker services started"
        else
            log "No docker-compose.yml found, skipping"
        fi
    else
        log "Docker not found, skipping"
    fi
}

# ============================================
# SETUP DATABASE
# ============================================

setup_database() {
    log "Setting up database"
    
    source venv/bin/activate
    
    # Run migrations
    if [ -f "alembic.ini" ]; then
        log "Running database migrations"
        alembic upgrade head
        success "Database migrations complete"
    fi
    
    # Seed database
    if [ -f "scripts/seed_database.py" ]; then
        log "Seeding database"
        python scripts/seed_database.py
        success "Database seeded"
    fi
}

# ============================================
# SETUP IDE CONFIGURATION
# ============================================

setup_vscode() {
    log "Setting up VS Code configuration"
    
    if [ ! -d ".vscode" ]; then
        mkdir -p .vscode
        
        # Create settings.json
        cat > .vscode/settings.json <<EOF
{
    "python.defaultInterpreterPath": "\${workspaceFolder}/venv/bin/python",
    "python.linting.enabled": true,
    "python.linting.pylintEnabled": false,
    "python.linting.flake8Enabled": true,
    "python.formatting.provider": "black",
    "python.testing.pytestEnabled": true,
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
        "source.organizeImports": true
    },
    "files.exclude": {
        "**/__pycache__": true,
        "**/.pytest_cache": true,
        "**/.mypy_cache": true,
        "**/venv": true
    }
}
EOF
        
        success "VS Code configuration created"
    else
        log ".vscode already exists"
    fi
}

# ============================================
# VERIFY SETUP
# ============================================

verify_setup() {
    log "Verifying setup"
    
    # Check if venv exists
    if [ -d "venv" ]; then
        success "Virtual environment exists"
    else
        echo "❌ Virtual environment missing"
        return 1
    fi
    
    # Check if .env exists
    if [ -f ".env" ]; then
        success ".env file exists"
    else
        echo "⚠️  .env file missing"
    fi
    
    # Check if dependencies are installed
    source venv/bin/activate
    if python -c "import fastapi" 2>/dev/null; then
        success "Dependencies installed"
    else
        echo "❌ Dependencies not installed"
        return 1
    fi
    
    success "Setup verification complete"
}

# ============================================
# MAIN EXECUTION
# ============================================

main() {
    echo "╔════════════════════════════════════════╗"
    echo "║  DEVELOPMENT ENVIRONMENT SETUP         ║"
    echo "╚════════════════════════════════════════╝"
    echo ""
    
    setup_venv
    install_dependencies
    setup_env
    setup_precommit
    setup_docker
    setup_database
    setup_vscode
    verify_setup
    
    echo ""
    echo "════════════════════════════════════════"
    echo "✨ Development environment ready!"
    echo "════════════════════════════════════════"
    echo ""
    echo "To start developing:"
    echo "  1. Activate virtual environment:"
    echo "     source venv/bin/activate"
    echo ""
    echo "  2. Start development server:"
    echo "     uvicorn main:app --reload"
    echo ""
    echo "  3. Or use Make:"
    echo "     make dev"
    echo ""
}

main
3. Makefile for Task Automation
makefile# Makefile
# =============================================================================
# DEVELOPMENT AUTOMATION
# =============================================================================
#
# Common development tasks automated with Make
#
# Usage:
#   make setup    - Initial setup
#   make dev      - Start development server
#   make test     - Run tests
#   make lint     - Run linters
#   make clean    - Clean up
#
# =============================================================================

.PHONY: help setup dev test lint format clean docker-up docker-down migrate seed

# Default target
.DEFAULT_GOAL := help

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[1;33m
NC := \033[0m # No Color

# Python
PYTHON := python3
VENV := venv
VENV_BIN := $(VENV)/bin

# =============================================================================
# HELP
# =============================================================================

help: ## Show this help message
	@echo "$(BLUE)Available commands:$(NC)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-15s$(NC) %s\n", $$1, $$2}'
	@echo ""

# =============================================================================
# SETUP & INSTALLATION
# =============================================================================

check: ## Check system requirements
	@echo "$(BLUE)Checking requirements...$(NC)"
	@bash scripts/check_requirements.sh

setup: ## Complete development environment setup
	@echo "$(BLUE)Setting up development environment...$(NC)"
	@bash scripts/setup_dev_environment.sh
	@echo "$(GREEN)✓ Setup complete!$(NC)"

venv: ## Create virtual environment
	@echo "$(BLUE)Creating virtual environment...$(NC)"
	@$(PYTHON) -m venv $(VENV)
	@$(VENV_BIN)/pip install --upgrade pip
	@echo "$(GREEN)✓ Virtual environment created$(NC)"

install: venv ## Install dependencies
	@echo "$(BLUE)Installing dependencies...$(NC)"
	@$(VENV_BIN)/pip install -r requirements.txt
	@$(VENV_BIN)/pip install -r requirements-dev.txt
	@echo "$(GREEN)✓ Dependencies installed$(NC)"

install-prod: venv ## Install production dependencies only
	@echo "$(BLUE)Installing production dependencies...$(NC)"
	@$(VENV_BIN)/pip install -r requirements.txt
	@echo "$(GREEN)✓ Production dependencies installed$(NC)"

# =============================================================================
# DEVELOPMENT
# =============================================================================

dev: ## Start development server with hot reload
	@echo "$(BLUE)Starting development server...$(NC)"
	@$(VENV_BIN)/uvicorn main:app --reload --host 0.0.0.0 --port 8000

dev-debug: ## Start development server with debugging
	@echo "$(BLUE)Starting development server (debug mode)...$(NC)"
	@$(VENV_BIN)/uvicorn main:app --reload --host 0.0.0.0 --port 8000 --log-level debug

shell: ## Start Python shell with app context
	@echo "$(BLUE)Starting Python shell...$(NC)"
	@$(VENV_BIN)/python -i -c "from main import app; from database import SessionLocal; db = SessionLocal()"

# =============================================================================
# DOCKER
# =============================================================================

docker-up: ## Start Docker services (PostgreSQL, Redis, MinIO)
	@echo "$(BLUE)Starting Docker services...$(NC)"
	@docker-compose up -d postgres redis minio
	@echo "$(GREEN)✓ Docker services started$(NC)"
	@echo "PostgreSQL: localhost:5432"
	@echo "Redis:      localhost:6379"
	@echo "MinIO:      localhost:9000 (Console: localhost:9001)"

docker-down: ## Stop Docker services
	@echo "$(BLUE)Stopping Docker services...$(NC)"
	@docker-compose down
	@echo "$(GREEN)✓ Docker services stopped$(NC)"

docker-logs: ## Show Docker logs
	@docker-compose logs -f

docker-clean: ## Remove Docker volumes and data
	@echo "$(YELLOW)⚠️  This will delete all data!$(NC)"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		docker-compose down -v; \
		echo "$(GREEN)✓ Docker volumes removed$(NC)"; \
	fi

# =============================================================================
# DATABASE
# =============================================================================

migrate: ## Run database migrations
	@echo "$(BLUE)Running database migrations...$(NC)"
	@$(VENV_BIN)/alembic upgrade head
	@echo "$(GREEN)✓ Migrations complete$(NC)"

migrate-create: ## Create new migration
	@echo "$(BLUE)Creating new migration...$(NC)"
	@read -p "Migration name: " name; \
	$(VENV_BIN)/alembic revision --autogenerate -m "$$name"

migrate-rollback: ## Rollback last migration
	@echo "$(BLUE)Rolling back migration...$(NC)"
	@$(VENV_BIN)/alembic downgrade -1
	@echo "$(GREEN)✓ Rollback complete$(NC)"

migrate-history: ## Show migration history
	@$(VENV_BIN)/alembic history

seed: ## Seed database with test data
	@echo "$(BLUE)Seeding database...$(NC)"
	@$(VENV_BIN)/python scripts/seed_database.py
	@echo "$(GREEN)✓ Database seeded$(NC)"

db-reset: ## Reset database (drop all tables and re-migrate)
	@echo "$(YELLOW)⚠️  This will delete all data!$(NC)"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		$(VENV_BIN)/alembic downgrade base; \
		$(VENV_BIN)/alembic upgrade head; \
		$(VENV_BIN)/python scripts/seed_database.py; \
		echo "$(GREEN)✓ Database reset$(NC)"; \
	fi

# =============================================================================
# TESTING
# =============================================================================

test: ## Run all tests
	@echo "$(BLUE)Running tests...$(NC)"
	@$(VENV_BIN)/pytest -v

test-watch: ## Run tests in watch mode
	@echo "$(BLUE)Running tests in watch mode...$(NC)"
	@$(VENV_BIN)/pytest-watch

test-cov: ## Run tests with coverage
	@echo "$(BLUE)Running tests with coverage...$(NC)"
	@$(VENV_BIN)/pytest --cov=. --cov-report=html --cov-report=term
	@echo "$(GREEN)✓ Coverage report: htmlcov/index.html$(NC)"

test-fast: ## Run tests without slow tests
	@echo "$(BLUE)Running fast tests...$(NC)"
	@$(VENV_BIN)/pytest -v -m "not slow"

# =============================================================================
# CODE QUALITY
# =============================================================================

lint: ## Run all linters
	@echo "$(BLUE)Running linters...$(NC)"
	@$(VENV_BIN)/ruff check .
	@$(VENV_BIN)/mypy .
	@echo "$(GREEN)✓ Linting complete$(NC)"

lint-fix: ## Fix auto-fixable linting issues
	@echo "$(BLUE)Fixing linting issues...$(NC)"
	@$(VENV_BIN)/ruff check --fix .
	@echo "$(GREEN)✓ Auto-fixes applied$(NC)"

format: ## Format code with black
	@echo "$(BLUE)Formatting code...$(NC)"
	@$(VENV_BIN)/black .
	@$(VENV_BIN)/isort .
	@echo "$(GREEN)✓ Code formatted$(NC)"

type-check: ## Run type checker
	@echo "$(BLUE)Running type checker...$(NC)"
	@$(VENV_BIN)/mypy .

pre-commit: ## Run pre-commit hooks on all files
	@echo "$(BLUE)Running pre-commit hooks...$(NC)"
	@$(VENV_BIN)/pre-commit run --all-files

# =============================================================================
# CLEANUP
# =============================================================================

clean: ## Remove generated files
	@echo "$(BLUE)Cleaning up...$(NC)"
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@rm -rf htmlcov .coverage 2>/dev/null || true
	@echo "$(GREEN)✓ Cleanup complete$(NC)"

clean-all: clean docker-clean ## Remove all generated files and Docker data
	@echo "$(BLUE)Deep cleaning...$(NC)"
	@rm -rf $(VENV)
	@echo "$(GREEN)✓ Deep cleanup complete$(NC)"

# =============================================================================
# DOCUMENTATION
# =============================================================================

docs: ## Generate API documentation
	@echo "$(BLUE)Generating documentation...$(NC)"
	@$(VENV_BIN)/python -c "from main import app; import json; print(json.dumps(app.openapi(), indent=2))" > openapi.json
	@echo "$(GREEN)✓ Documentation generated: openapi.json$(NC)"

docs-serve: ## Serve documentation locally
	@echo "$(BLUE)Serving documentation at http://localhost:8000/docs$(NC)"
	@$(VENV_BIN)/uvicorn main:app --reload

# =============================================================================
# UTILITIES
# =============================================================================

freeze: ## Generate requirements.txt from current environment
	@echo "$(BLUE)Freezing requirements...$(NC)"
	@$(VENV_BIN)/pip freeze > requirements-frozen.txt
	@echo "$(GREEN)✓ Requirements saved to requirements-frozen.txt$(NC)"

update: ## Update all dependencies
	@echo "$(BLUE)Updating dependencies...$(NC)"
	@$(VENV_BIN)/pip install --upgrade -r requirements.txt -r requirements-dev.txt
	@echo "$(GREEN)✓ Dependencies updated$(NC)"

check-security: ## Check for security vulnerabilities
	@echo "$(BLUE)Checking for security issues...$(NC)"
	@$(VENV_BIN)/safety check
	@$(VENV_BIN)/bandit -r . -x ./venv,./tests

env-example: ## Generate .env.example from .env
	@echo "$(BLUE)Generating .env.example...$(NC)"
	@sed 's/=.*/=/' .env > .env.example
	@echo "$(GREEN)✓ .env.example generated$(NC)"

# =============================================================================
# DEPLOYMENT
# =============================================================================

build: ## Build Docker image
	@echo "$(BLUE)Building Docker image...$(NC)"
	@docker build -t myapp:latest .
	@echo "$(GREEN)✓ Docker image built$(NC)"

run-prod: ## Run in production mode
	@echo "$(BLUE)Starting production server...$(NC)"
	@$(VENV_BIN)/gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000

💻 IDE CONFIGURATION
1. VS Code Configuration
json// .vscode/settings.json

{
  // Python Configuration
  "python.defaultInterpreterPath": "${workspaceFolder}/venv/bin/python",
  "python.terminal.activateEnvironment": true,
  
  // Linting
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": false,
  "python.linting.flake8Enabled": false,
  "python.linting.mypyEnabled": true,
  
  // Use Ruff for linting (modern, fast)
  "ruff.enable": true,
  "ruff.organizeImports": true,
  
  // Formatting
  "python.formatting.provider": "black",
  "python.formatting.blackArgs": ["--line-length", "100"],
  
  // Editor
  "editor.formatOnSave": true,
  "editor.codeActionsOnSave": {
    "source.organizeImports": true,
    "source.fixAll": true
  },
  "editor.rulers": [100],
  
  // Testing
  "python.testing.pytestEnabled": true,
  "python.testing.unittestEnabled": false,
  "python.testing.pytestArgs": [
    "tests",
    "-v",
    "--tb=short"
  ],
  
  // Type Checking
  "python.analysis.typeCheckingMode": "basic",
  "python.analysis.autoImportCompletions": true,
  
  // Files
  "files.exclude": {
    "**/__pycache__": true,
    "**/.pytest_cache": true,
    "**/.mypy_cache": true,
    "**/.ruff_cache": true,
    "**/venv": true,
    "**/*.pyc": true,
    "**/.coverage": true,
    "**/htmlcov": true
  },
  
  "files.watcherExclude": {
    "**/__pycache__/**": true,
    "**/venv/**": true
  },
  
  // Auto Save
  "files.autoSave": "afterDelay",
  "files.autoSaveDelay": 1000,
  
  // Terminal
  "terminal.integrated.env.linux": {
    "PYTHONPATH": "${workspaceFolder}"
  },
  "terminal.integrated.env.osx": {
    "PYTHONPATH": "${workspaceFolder}"
  },
  "terminal.integrated.env.windows": {
    "PYTHONPATH": "${workspaceFolder}"
  },
  
  // Git
  "git.autofetch": true,
  "git.confirmSync": false,
  
  // Search
  "search.exclude": {
    "**/venv": true,
    "**/__pycache__": true,
    "**/.pytest_cache": true,
    "**/.mypy_cache": true
  }
}
json// .vscode/extensions.json
// Recommended VS Code extensions

{
  "recommendations": [
    "ms-python.python",
    "ms-python.vscode-pylance",
    "charliermarsh.ruff",
    "ms-python.black-formatter",
    "ms-python.isort",
    "mtxr.sqltools",
    "mtxr.sqltools-driver-pg",
    "ms-azuretools.vscode-docker",
    "eamodio.gitlens",
    "streetsidesoftware.code-spell-checker",
    "usernamehw.errorlens",
    "wayou.vscode-todo-highlight",
    "gruntfuggly.todo-tree",
    "tamasfe.even-better-toml",
    "redhat.vscode-yaml"
  ]
}
json// .vscode/launch.json
// Debug configurations

{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Python: FastAPI",
      "type": "python",
      "request": "launch",
      "module": "uvicorn",
      "args": [
        "main:app",
        "--reload",
        "--host",
        "0.0.0.0",
        "--port",
        "8000"
      ],
      "jinja": true,
      "justMyCode": false,
      "env": {
        "PYTHONPATH": "${workspaceFolder}"
      }
    },
    {
      "name": "Python: Current File",
      "type": "python",
      "request": "launch",
      "program": "${file}",
      "console": "integratedTerminal",
      "justMyCode": false
    },
    {
      "name": "Python: Debug Tests",
      "type": "python",
      "request": "launch",
      "module": "pytest",
      "args": [
        "-v",
        "--tb=short",
        "${file}"
      ],
      "console": "integratedTerminal",
      "justMyCode": false
    },
    {
      "name": "Python: Celery Worker",
      "type": "python",
      "request": "launch",
      "module": "celery",
      "args": [
        "-A",
        "worker",
        "worker",
        "--loglevel=info"
      ],
      "console": "integratedTerminal"
    }
  ]
}
json// .vscode/tasks.json
// Common tasks

{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "Start Dev Server",
      "type": "shell",
      "command": "make dev",
      "problemMatcher": [],
      "group": {
        "kind": "build",
        "isDefault": true
      }
    },
    {
      "label": "Run Tests",
      "type": "shell",
      "command": "make test",
      "problemMatcher": []
    },
    {
      "label": "Format Code",
      "type": "shell",
      "command": "make format",
      "problemMatcher": []
    },
    {
      "label": "Lint Code",
      "type": "shell",
      "command": "make lint",
      "problemMatcher": []
    },
    {
      "label": "Docker Up",
      "type": "shell",
      "command": "make docker-up",
      "problemMatcher": []
    },
    {
      "label": "Run Migrations",
      "type": "shell",
      "command": "make migrate",
      "problemMatcher": []
    }
  ]
}
2. PyCharm Configuration
xml<!-- .idea/runConfigurations/FastAPI_Dev.xml -->

<component name="ProjectRunConfigurationManager">
  <configuration default="false" name="FastAPI Dev" type="PythonConfigurationType" factoryName="Python">
    <module name="myproject" />
    <option name="INTERPRETER_OPTIONS" value="" />
    <option name="PARENT_ENVS" value="true" />
    <envs>
      <env name="PYTHONUNBUFFERED" value="1" />
      <env name="PYTHONPATH" value="$PROJECT_DIR$" />
    </envs>
    <option name="SDK_HOME" value="$PROJECT_DIR$/venv/bin/python" />
    <option name="WORKING_DIRECTORY" value="$PROJECT_DIR$" />
    <option name="IS_MODULE_SDK" value="false" />
    <option name="ADD_CONTENT_ROOTS" value="true" />
    <option name="ADD_SOURCE_ROOTS" value="true" />
    <EXTENSION ID="PythonCoverageRunConfigurationExtension" runner="coverage.py" />
    <option name="SCRIPT_NAME" value="$USER_HOME$/.local/bin/uvicorn" />
    <option name="PARAMETERS" value="main:app --reload --host 0.0.0.0 --port 8000" />
    <option name="SHOW_COMMAND_LINE" value="false" />
    <option name="EMULATE_TERMINAL" value="false" />
    <option name="MODULE_MODE" value="false" />
    <option name="REDIRECT_INPUT" value="false" />
    <option name="INPUT_FILE" value="" />
    <method v="2" />
  </configuration>
</component>

🐍 VIRTUAL ENVIRONMENT SETUP
1. Using venv (Built-in)
bash#!/bin/bash
# scripts/setup_venv.sh

# ============================================
# VIRTUAL ENVIRONMENT SETUP (venv)
# ============================================

# Create virtual environment
python3 -m venv venv

# Activate (Linux/macOS)
source venv/bin/activate

# Activate (Windows)
# venv\Scripts\activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Verify installation
python --version
pip list

echo "✓ Virtual environment ready!"
2. Using pyenv (Multiple Python Versions)
bash#!/bin/bash
# scripts/setup_pyenv.sh

# ============================================
# PYENV SETUP (Multiple Python Versions)
# ============================================

# Install pyenv (if not installed)
if ! command -v pyenv &> /dev/null; then
    echo "Installing pyenv..."
    curl https://pyenv.run | bash
    
    # Add to shell profile
    echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.bashrc
    echo 'export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.bashrc
    echo 'eval "$(pyenv init --path)"' >> ~/.bashrc
    echo 'eval "$(pyenv init -)"' >> ~/.bashrc
    
    source ~/.bashrc
fi

# Install Python 3.11
pyenv install 3.11.7

# Set as project Python
pyenv local 3.11.7

# Create virtualenv
pyenv virtualenv 3.11.7 myproject-env

# Activate
pyenv activate myproject-env

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-dev.txt

echo "✓ Pyenv environment ready!"
3. Using Poetry (Modern Dependency Management)
toml# pyproject.toml

[tool.poetry]
name = "myproject"
version = "0.1.0"
description = "OCR Document Processing System"
authors = ["Your Name <your.email@example.com>"]
readme = "README.md"
python = "^3.11"

[tool.poetry.dependencies]
python = "^3.11"
fastapi = "^0.109.0"
uvicorn = {extras = ["standard"], version = "^0.27.0"}
sqlalchemy = "^2.0.25"
alembic = "^1.13.1"
psycopg2-binary = "^2.9.9"
redis = "^5.0.1"
celery = "^5.3.6"
python-multipart = "^0.0.6"
python-jose = {extras = ["cryptography"], version = "^3.3.0"}
passlib = {extras = ["bcrypt"], version = "^1.7.4"}
boto3 = "^1.34.34"
pillow = "^10.2.0"
pydantic = {extras = ["email"], version = "^2.5.3"}
pydantic-settings = "^2.1.0"
loguru = "^0.7.2"

[tool.poetry.group.dev.dependencies]
pytest = "^7.4.4"
pytest-cov = "^4.1.0"
pytest-asyncio = "^0.23.3"
black = "^23.12.1"
isort = "^5.13.2"
ruff = "^0.1.14"
mypy = "^1.8.0"
pre-commit = "^3.6.0"
httpx = "^0.26.0"
faker = "^22.6.0"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"

[tool.black]
line-length = 100
target-version = ['py311']
include = '\.pyi?$'

[tool.isort]
profile = "black"
line_length = 100

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = "test_*.py"
python_functions = "test_*"
addopts = "-v --tb=short --strict-markers"

[tool.mypy]
python_version = "3.11"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
bash#!/bin/bash
# scripts/setup_poetry.sh

# Install Poetry
curl -sSL https://install.python-poetry.org | python3 -

# Configure Poetry
poetry config virtualenvs.in-project true

# Install dependencies
poetry install

# Activate shell
poetry shell

# Run commands
poetry run uvicorn main:app --reload

# Add new dependency
poetry add requests

# Add dev dependency
poetry add --group dev pytest

echo "✓ Poetry environment ready!"


DEVELOPMENT SETUP & ENVIRONMENT GUIDE - TEIL 2
Environment Variables, Database Seeding, Debugging & Git Workflow

📋 TABLE OF CONTENTS (TEIL 2)

Environment Variables
Database Seeding
Hot Reload & Debugging
Git Workflow


🔐 ENVIRONMENT VARIABLES
1. Environment Configuration Management
python# config/settings.py

"""
Application Settings with Pydantic

Features:
- Type-safe configuration
- Environment-based settings
- Secret management
- Validation
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, PostgresDsn, RedisDsn, validator
from typing import Optional, List
from functools import lru_cache
import os


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables
    
    Supports multiple environments:
    - development
    - testing
    - staging
    - production
    """
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # ============================================
    # APPLICATION
    # ============================================
    
    APP_NAME: str = "OCR Document Processing System"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = Field(default="development", description="Environment name")
    DEBUG: bool = Field(default=True, description="Debug mode")
    
    # API Configuration
    API_V1_PREFIX: str = "/api/v1"
    API_TITLE: str = "OCR API"
    API_DESCRIPTION: str = "OCR Document Processing API"
    
    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 4
    
    # CORS
    CORS_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"],
        description="Allowed CORS origins"
    )
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: List[str] = ["*"]
    CORS_ALLOW_HEADERS: List[str] = ["*"]
    
    # ============================================
    # DATABASE
    # ============================================
    
    # PostgreSQL
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "ocr_db"
    
    DATABASE_URL: Optional[PostgresDsn] = None
    
    @validator("DATABASE_URL", pre=True)
    def assemble_db_connection(cls, v: Optional[str], values: dict) -> str:
        """Build database URL from components"""
        if isinstance(v, str):
            return v
        
        return f"postgresql://{values['POSTGRES_USER']}:{values['POSTGRES_PASSWORD']}@" \
               f"{values['POSTGRES_SERVER']}:{values['POSTGRES_PORT']}/{values['POSTGRES_DB']}"
    
    # Database Pool Settings
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 3600
    
    # ============================================
    # REDIS
    # ============================================
    
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None
    
    REDIS_URL: Optional[str] = None
    
    @validator("REDIS_URL", pre=True)
    def assemble_redis_connection(cls, v: Optional[str], values: dict) -> str:
        """Build Redis URL from components"""
        if isinstance(v, str):
            return v
        
        if values.get('REDIS_PASSWORD'):
            return f"redis://:{values['REDIS_PASSWORD']}@{values['REDIS_HOST']}:" \
                   f"{values['REDIS_PORT']}/{values['REDIS_DB']}"
        
        return f"redis://{values['REDIS_HOST']}:{values['REDIS_PORT']}/{values['REDIS_DB']}"
    
    # ============================================
    # CELERY
    # ============================================
    
    CELERY_BROKER_URL: Optional[str] = None
    CELERY_RESULT_BACKEND: Optional[str] = None
    
    @validator("CELERY_BROKER_URL", pre=True)
    def set_celery_broker(cls, v: Optional[str], values: dict) -> str:
        """Set Celery broker URL"""
        return v or values.get('REDIS_URL')
    
    @validator("CELERY_RESULT_BACKEND", pre=True)
    def set_celery_backend(cls, v: Optional[str], values: dict) -> str:
        """Set Celery result backend"""
        return v or values.get('REDIS_URL')
    
    # ============================================
    # SECURITY
    # ============================================
    
    # JWT
    SECRET_KEY: str = Field(
        default="CHANGE_ME_IN_PRODUCTION",
        description="Secret key for JWT encoding"
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # Password
    PASSWORD_MIN_LENGTH: int = 8
    PASSWORD_REQUIRE_UPPERCASE: bool = True
    PASSWORD_REQUIRE_LOWERCASE: bool = True
    PASSWORD_REQUIRE_DIGIT: bool = True
    PASSWORD_REQUIRE_SPECIAL: bool = True
    
    # ============================================
    # STORAGE
    # ============================================
    
    # Local Storage
    LOCAL_STORAGE_PATH: str = "/var/app/storage"
    UPLOAD_MAX_SIZE_MB: int = 100
    
    # S3/MinIO
    S3_ENABLED: bool = False
    S3_ENDPOINT: Optional[str] = None  # For MinIO
    S3_REGION: str = "eu-central-1"
    S3_BUCKET: str = "ocr-uploads"
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    
    # MinIO (local S3-compatible)
    MINIO_ENABLED: bool = True
    MINIO_ENDPOINT: str = "http://localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "ocr-uploads"
    MINIO_SECURE: bool = False
    
    # ============================================
    # CDN
    # ============================================
    
    CDN_ENABLED: bool = False
    CDN_TYPE: str = "cloudfront"  # cloudfront, cloudflare
    CDN_DOMAIN: Optional[str] = None
    CLOUDFRONT_DISTRIBUTION_ID: Optional[str] = None
    CLOUDFRONT_KEY_PAIR_ID: Optional[str] = None
    CLOUDFRONT_PRIVATE_KEY_PATH: Optional[str] = None
    
    # ============================================
    # OCR
    # ============================================
    
    # GPU Backend A (DeepSeek)
    OCR_GPU_A_ENABLED: bool = True
    OCR_GPU_A_MODEL: str = "deepseek-ai/Janus-Pro-7B"
    OCR_GPU_A_DEVICE: str = "cuda:0"
    OCR_GPU_A_MAX_BATCH_SIZE: int = 4
    
    # GPU Backend B (GOT-OCR)
    OCR_GPU_B_ENABLED: bool = True
    OCR_GPU_B_MODEL: str = "ucaslcl/GOT-OCR2_0"
    OCR_GPU_B_DEVICE: str = "cuda:0"
    
    # CPU Backend (Surya + Docling)
    OCR_CPU_ENABLED: bool = True
    OCR_CPU_WORKERS: int = 4
    
    # Processing
    OCR_QUEUE_NAME: str = "ocr_processing"
    OCR_MAX_RETRIES: int = 3
    OCR_TIMEOUT_SECONDS: int = 300
    
    # ============================================
    # VIRUS SCANNING
    # ============================================
    
    CLAMAV_ENABLED: bool = True
    CLAMAV_HOST: str = "localhost"
    CLAMAV_PORT: int = 3310
    
    # ============================================
    # LOGGING
    # ============================================
    
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # json, text
    LOG_FILE: Optional[str] = "/var/log/app/app.log"
    LOG_ROTATION: str = "500 MB"
    LOG_RETENTION: str = "30 days"
    
    # Sentry
    SENTRY_ENABLED: bool = False
    SENTRY_DSN: Optional[str] = None
    SENTRY_ENVIRONMENT: Optional[str] = None
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1
    
    # ============================================
    # EMAIL
    # ============================================
    
    EMAIL_ENABLED: bool = False
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_EMAIL: Optional[str] = None
    SMTP_FROM_NAME: Optional[str] = None
    
    # ============================================
    # MONITORING
    # ============================================
    
    # Prometheus
    PROMETHEUS_ENABLED: bool = False
    PROMETHEUS_PORT: int = 9090
    
    # ============================================
    # FEATURE FLAGS
    # ============================================
    
    FEATURE_OCR_BATCH_PROCESSING: bool = True
    FEATURE_AUTO_TRANSLATION: bool = False
    FEATURE_DOCUMENT_COMPARISON: bool = False
    
    # ============================================
    # RATE LIMITING
    # ============================================
    
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_PER_HOUR: int = 1000
    
    # ============================================
    # VALIDATORS
    # ============================================
    
    @validator("ENVIRONMENT")
    def validate_environment(cls, v: str) -> str:
        """Validate environment name"""
        allowed = ["development", "testing", "staging", "production"]
        if v not in allowed:
            raise ValueError(f"Environment must be one of: {allowed}")
        return v
    
    @validator("SECRET_KEY")
    def validate_secret_key(cls, v: str, values: dict) -> str:
        """Validate secret key in production"""
        if values.get('ENVIRONMENT') == 'production' and v == 'CHANGE_ME_IN_PRODUCTION':
            raise ValueError("SECRET_KEY must be changed in production!")
        return v
    
    # ============================================
    # PROPERTIES
    # ============================================
    
    @property
    def is_development(self) -> bool:
        """Check if running in development"""
        return self.ENVIRONMENT == "development"
    
    @property
    def is_production(self) -> bool:
        """Check if running in production"""
        return self.ENVIRONMENT == "production"
    
    @property
    def is_testing(self) -> bool:
        """Check if running in testing"""
        return self.ENVIRONMENT == "testing"


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance
    
    Uses LRU cache to avoid re-reading .env file
    """
    return Settings()


# Convenience
settings = get_settings()


# Example usage
if __name__ == "__main__":
    settings = get_settings()
    
    print(f"Environment: {settings.ENVIRONMENT}")
    print(f"Debug: {settings.DEBUG}")
    print(f"Database URL: {settings.DATABASE_URL}")
    print(f"Redis URL: {settings.REDIS_URL}")
2. Environment File Templates
bash# .env.example
# ============================================
# ENVIRONMENT VARIABLES TEMPLATE
# ============================================
#
# Copy this file to .env and configure:
#   cp .env.example .env
#
# Never commit .env to version control!
# ============================================

# ============================================
# APPLICATION
# ============================================

APP_NAME=OCR Document Processing System
APP_VERSION=0.1.0
ENVIRONMENT=development
DEBUG=true

# Server
HOST=0.0.0.0
PORT=8000
WORKERS=4

# CORS (comma-separated)
CORS_ORIGINS=http://localhost:3000,http://localhost:8000

# ============================================
# DATABASE
# ============================================

POSTGRES_SERVER=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=ocr_db

# Or full connection string
# DATABASE_URL=postgresql://user:password@localhost:5432/ocr_db

# ============================================
# REDIS
# ============================================

REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# Or full connection string
# REDIS_URL=redis://localhost:6379/0

# ============================================
# SECURITY
# ============================================

# JWT Secret (CHANGE IN PRODUCTION!)
SECRET_KEY=your-secret-key-here-change-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# ============================================
# STORAGE
# ============================================

# Local Storage
LOCAL_STORAGE_PATH=/var/app/storage
UPLOAD_MAX_SIZE_MB=100

# MinIO (Local S3-compatible)
MINIO_ENABLED=true
MINIO_ENDPOINT=http://localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=ocr-uploads

# AWS S3 (Production)
S3_ENABLED=false
S3_REGION=eu-central-1
S3_BUCKET=ocr-uploads
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=

# ============================================
# OCR CONFIGURATION
# ============================================

# GPU Backend A (DeepSeek)
OCR_GPU_A_ENABLED=true
OCR_GPU_A_MODEL=deepseek-ai/Janus-Pro-7B
OCR_GPU_A_DEVICE=cuda:0

# GPU Backend B (GOT-OCR)
OCR_GPU_B_ENABLED=true
OCR_GPU_B_MODEL=ucaslcl/GOT-OCR2_0

# CPU Backend
OCR_CPU_ENABLED=true
OCR_CPU_WORKERS=4

# ============================================
# VIRUS SCANNING
# ============================================

CLAMAV_ENABLED=true
CLAMAV_HOST=localhost
CLAMAV_PORT=3310

# ============================================
# LOGGING
# ============================================

LOG_LEVEL=INFO
LOG_FORMAT=json
LOG_FILE=/var/log/app/app.log

# Sentry (Optional)
SENTRY_ENABLED=false
SENTRY_DSN=
SENTRY_ENVIRONMENT=development

# ============================================
# EMAIL (Optional)
# ============================================

EMAIL_ENABLED=false
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM_EMAIL=
SMTP_FROM_NAME=

# ============================================
# FEATURE FLAGS
# ============================================

FEATURE_OCR_BATCH_PROCESSING=true
FEATURE_AUTO_TRANSLATION=false
FEATURE_DOCUMENT_COMPARISON=false

# ============================================
# RATE LIMITING
# ============================================

RATE_LIMIT_ENABLED=true
RATE_LIMIT_PER_MINUTE=60
RATE_LIMIT_PER_HOUR=1000
bash# .env.production.example
# Production environment template

ENVIRONMENT=production
DEBUG=false

# Use strong secret key!
SECRET_KEY=GENERATE_STRONG_SECRET_KEY_HERE

# Production database
DATABASE_URL=postgresql://prod_user:strong_password@prod-db.example.com:5432/ocr_prod

# Production Redis
REDIS_URL=redis://:redis_password@prod-redis.example.com:6379/0

# AWS S3
S3_ENABLED=true
S3_REGION=eu-central-1
S3_BUCKET=ocr-prod-uploads
AWS_ACCESS_KEY_ID=YOUR_AWS_KEY
AWS_SECRET_ACCESS_KEY=YOUR_AWS_SECRET

# Sentry
SENTRY_ENABLED=true
SENTRY_DSN=https://your-sentry-dsn@sentry.io/project
SENTRY_ENVIRONMENT=production

# Production CORS
CORS_ORIGINS=https://app.example.com,https://www.example.com

# Logging
LOG_LEVEL=WARNING
LOG_FILE=/var/log/ocr/app.log
3. Environment Management Script
python# scripts/manage_env.py

"""
Environment Variable Management Script

Usage:
    python manage_env.py check          # Validate .env
    python manage_env.py generate       # Generate .env from template
    python manage_env.py diff           # Compare .env with .env.example
    python manage_env.py export         # Export as shell script
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple
from dotenv import dotenv_values
import click


class EnvManager:
    """Manage environment variables"""
    
    def __init__(self, project_root: Path = None):
        self.project_root = project_root or Path.cwd()
        self.env_file = self.project_root / ".env"
        self.env_example = self.project_root / ".env.example"
    
    def check(self) -> bool:
        """
        Validate .env file
        
        - Check if .env exists
        - Verify required variables
        - Check for sensitive data
        """
        
        if not self.env_file.exists():
            click.echo(click.style("✗ .env file not found", fg="red"))
            click.echo(f"  Create it from template: cp .env.example .env")
            return False
        
        # Load variables
        env_vars = dotenv_values(self.env_file)
        
        # Required variables
        required = [
            "ENVIRONMENT",
            "SECRET_KEY",
            "DATABASE_URL",
            "REDIS_URL"
        ]
        
        missing = []
        for var in required:
            if var not in env_vars or not env_vars[var]:
                missing.append(var)
        
        if missing:
            click.echo(click.style("✗ Missing required variables:", fg="red"))
            for var in missing:
                click.echo(f"  - {var}")
            return False
        
        # Check for default values in production
        if env_vars.get("ENVIRONMENT") == "production":
            dangerous = []
            
            if "CHANGE_ME" in env_vars.get("SECRET_KEY", ""):
                dangerous.append("SECRET_KEY still has default value")
            
            if env_vars.get("POSTGRES_PASSWORD") == "postgres":
                dangerous.append("POSTGRES_PASSWORD is default")
            
            if dangerous:
                click.echo(click.style("⚠ Dangerous settings in production:", fg="yellow"))
                for issue in dangerous:
                    click.echo(f"  - {issue}")
                return False
        
        click.echo(click.style("✓ .env validation passed", fg="green"))
        return True
    
    def generate(self, force: bool = False):
        """Generate .env from .env.example"""
        
        if self.env_file.exists() and not force:
            click.echo(click.style("✗ .env already exists", fg="red"))
            click.echo("  Use --force to overwrite")
            return
        
        if not self.env_example.exists():
            click.echo(click.style("✗ .env.example not found", fg="red"))
            return
        
        # Copy template
        import shutil
        shutil.copy(self.env_example, self.env_file)
        
        click.echo(click.style("✓ Created .env from template", fg="green"))
        click.echo("\n⚠ Don't forget to configure:")
        click.echo("  - SECRET_KEY")
        click.echo("  - Database credentials")
        click.echo("  - Storage credentials")
    
    def diff(self):
        """Compare .env with .env.example"""
        
        if not self.env_file.exists():
            click.echo(click.style("✗ .env not found", fg="red"))
            return
        
        if not self.env_example.exists():
            click.echo(click.style("✗ .env.example not found", fg="red"))
            return
        
        env_vars = set(dotenv_values(self.env_file).keys())
        example_vars = set(dotenv_values(self.env_example).keys())
        
        # Missing in .env
        missing = example_vars - env_vars
        if missing:
            click.echo(click.style("Variables in .env.example but not in .env:", fg="yellow"))
            for var in sorted(missing):
                click.echo(f"  + {var}")
            click.echo()
        
        # Extra in .env
        extra = env_vars - example_vars
        if extra:
            click.echo(click.style("Variables in .env but not in .env.example:", fg="blue"))
            for var in sorted(extra):
                click.echo(f"  - {var}")
            click.echo()
        
        if not missing and not extra:
            click.echo(click.style("✓ .env and .env.example are in sync", fg="green"))
    
    def export_shell(self, output: Path = None):
        """Export as shell script"""
        
        if not self.env_file.exists():
            click.echo(click.style("✗ .env not found", fg="red"))
            return
        
        env_vars = dotenv_values(self.env_file)
        
        output_file = output or self.project_root / "env.sh"
        
        with open(output_file, 'w') as f:
            f.write("#!/bin/bash\n")
            f.write("# Auto-generated from .env\n")
            f.write("# Usage: source env.sh\n\n")
            
            for key, value in env_vars.items():
                # Escape special characters
                safe_value = value.replace('"', '\\"')
                f.write(f'export {key}="{safe_value}"\n')
        
        # Make executable
        output_file.chmod(0o755)
        
        click.echo(click.style(f"✓ Exported to {output_file}", fg="green"))


@click.group()
def cli():
    """Environment variable management"""
    pass


@cli.command()
def check():
    """Validate .env file"""
    manager = EnvManager()
    success = manager.check()
    sys.exit(0 if success else 1)


@cli.command()
@click.option('--force', is_flag=True, help='Overwrite existing .env')
def generate(force):
    """Generate .env from template"""
    manager = EnvManager()
    manager.generate(force=force)


@cli.command()
def diff():
    """Compare .env with .env.example"""
    manager = EnvManager()
    manager.diff()


@cli.command()
@click.option('--output', type=click.Path(), help='Output file')
def export(output):
    """Export as shell script"""
    manager = EnvManager()
    manager.export_shell(Path(output) if output else None)


if __name__ == '__main__':
    cli()

🗄️ DATABASE SEEDING
1. Database Seeder
python# scripts/seed_database.py

"""
Database Seeding Script

Seeds database with test data for development

Usage:
    python scripts/seed_database.py
    python scripts/seed_database.py --clear  # Clear before seeding
"""

from sqlalchemy.orm import Session
from faker import Faker
from passlib.context import CryptContext
import click
from pathlib import Path
import sys
from datetime import datetime, timedelta
import random

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import SessionLocal, engine
from models.user import User, Role
from models.file import File
from models.document import Document
from loguru import logger


# Initialize
fake = Faker(['de_DE', 'en_US'])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class DatabaseSeeder:
    """Database seeder for development data"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def clear_all(self):
        """Clear all data from database"""
        
        logger.warning("Clearing all database data...")
        
        # Delete in reverse order of dependencies
        self.db.query(File).delete()
        self.db.query(Document).delete()
        self.db.query(User).delete()
        self.db.query(Role).delete()
        
        self.db.commit()
        
        logger.info("✓ Database cleared")
    
    def seed_roles(self) -> dict:
        """Create default roles"""
        
        logger.info("Seeding roles...")
        
        roles_data = [
            {
                "name": "admin",
                "description": "System administrator",
                "permissions": ["*"]  # All permissions
            },
            {
                "name": "user",
                "description": "Regular user",
                "permissions": ["read:own", "write:own"]
            },
            {
                "name": "premium",
                "description": "Premium user",
                "permissions": ["read:own", "write:own", "ocr:batch"]
            }
        ]
        
        roles = {}
        
        for role_data in roles_data:
            role = Role(**role_data)
            self.db.add(role)
            roles[role_data["name"]] = role
        
        self.db.commit()
        
        logger.info(f"✓ Created {len(roles)} roles")
        
        return roles
    
    def seed_users(self, roles: dict, count: int = 20) -> list:
        """Create test users"""
        
        logger.info(f"Seeding {count} users...")
        
        users = []
        
        # Create admin user
        admin = User(
            email="admin@example.com",
            username="admin",
            full_name="System Administrator",
            hashed_password=pwd_context.hash("admin123"),
            is_active=True,
            is_verified=True,
            subscription_tier="enterprise",
            role_id=roles["admin"].id
        )
        self.db.add(admin)
        users.append(admin)
        
        # Create test user
        test_user = User(
            email="user@example.com",
            username="testuser",
            full_name="Test User",
            hashed_password=pwd_context.hash("test123"),
            is_active=True,
            is_verified=True,
            subscription_tier="pro",
            role_id=roles["premium"].id
        )
        self.db.add(test_user)
        users.append(test_user)
        
        # Create random users
        tiers = ["free", "basic", "pro"]
        role_names = ["user", "premium"]
        
        for i in range(count - 2):
            user = User(
                email=fake.email(),
                username=fake.user_name(),
                full_name=fake.name(),
                hashed_password=pwd_context.hash("password123"),
                is_active=random.choice([True, True, True, False]),  # 75% active
                is_verified=random.choice([True, True, False]),  # 66% verified
                subscription_tier=random.choice(tiers),
                role_id=roles[random.choice(role_names)].id,
                created_at=fake.date_time_between(start_date="-1y", end_date="now")
            )
            self.db.add(user)
            users.append(user)
        
        self.db.commit()
        
        # Refresh to get IDs
        for user in users:
            self.db.refresh(user)
        
        logger.info(f"✓ Created {len(users)} users")
        logger.info(f"  - Admin: admin@example.com / admin123")
        logger.info(f"  - Test:  user@example.com / test123")
        
        return users
    
    def seed_files(self, users: list, count: int = 100) -> list:
        """Create test file records"""
        
        logger.info(f"Seeding {count} files...")
        
        files = []
        
        categories = ["image", "document", "avatar", "temp"]
        mime_types = {
            "image": ["image/jpeg", "image/png", "image/webp"],
            "document": ["application/pdf", "application/msword"],
            "avatar": ["image/jpeg", "image/png"],
            "temp": ["image/jpeg", "application/pdf"]
        }
        
        for i in range(count):
            category = random.choice(categories)
            user = random.choice(users)
            
            # Random date in last 6 months
            created = fake.date_time_between(start_date="-6M", end_date="now")
            
            # Some files accessed recently
            if random.random() > 0.3:  # 70% accessed
                accessed = fake.date_time_between(
                    start_date=created,
                    end_date="now"
                )
            else:
                accessed = None
            
            file = File(
                uuid=fake.uuid4(),
                filename=f"{fake.word()}_{i}.{random.choice(['jpg', 'png', 'pdf'])}",
                original_filename=fake.file_name(),
                storage_type=random.choice(["s3", "local"]),
                storage_path=f"uploads/2024/{random.randint(1,12):02d}/{fake.uuid4()}.jpg",
                storage_bucket="ocr-uploads" if random.random() > 0.5 else None,
                size=random.randint(1000, 10000000),  # 1KB - 10MB
                mime_type=random.choice(mime_types[category]),
                user_id=user.id,
                category=category,
                is_public=random.choice([True, False]),
                is_processed=random.choice([True, True, False]),  # 66% processed
                created_at=created,
                accessed_at=accessed,
                metadata={
                    "width": random.randint(800, 3000),
                    "height": random.randint(600, 2000)
                } if category in ["image", "avatar"] else {}
            )
            
            self.db.add(file)
            files.append(file)
        
        self.db.commit()
        
        logger.info(f"✓ Created {len(files)} files")
        
        return files
    
    def seed_documents(self, users: list, files: list, count: int = 50) -> list:
        """Create test OCR documents"""
        
        logger.info(f"Seeding {count} documents...")
        
        documents = []
        
        languages = ["de", "en", "de,en"]
        statuses = ["pending", "processing", "completed", "failed"]
        doc_types = ["invoice", "contract", "letter", "form", "other"]
        
        for i in range(count):
            user = random.choice(users)
            file = random.choice([f for f in files if f.category == "document"])
            
            status = random.choice(statuses)
            
            # Completed documents have OCR text
            if status == "completed":
                ocr_text = fake.text(max_nb_chars=500)
                confidence = random.uniform(0.85, 0.99)
            else:
                ocr_text = None
                confidence = None
            
            document = Document(
                uuid=fake.uuid4(),
                title=f"Document {i+1} - {fake.catch_phrase()}",
                file_id=file.id,
                user_id=user.id,
                language=random.choice(languages),
                status=status,
                document_type=random.choice(doc_types),
                ocr_text=ocr_text,
                confidence=confidence,
                page_count=random.randint(1, 20),
                created_at=fake.date_time_between(start_date="-3M", end_date="now"),
                processed_at=datetime.now() if status == "completed" else None,
                metadata={
                    "backend": random.choice(["gpu_a", "gpu_b", "cpu"]),
                    "processing_time": random.uniform(1.0, 30.0)
                } if status == "completed" else {}
            )
            
            self.db.add(document)
            documents.append(document)
        
        self.db.commit()
        
        logger.info(f"✓ Created {len(documents)} documents")
        
        return documents
    
    def seed_all(
        self,
        users_count: int = 20,
        files_count: int = 100,
        documents_count: int = 50
    ):
        """Seed all data"""
        
        logger.info("Starting database seeding...")
        
        # Seed in order
        roles = self.seed_roles()
        users = self.seed_users(roles, count=users_count)
        files = self.seed_files(users, count=files_count)
        documents = self.seed_documents(users, files, count=documents_count)
        
        logger.info("✓ Database seeding complete!")
        logger.info(f"  - Roles: {len(roles)}")
        logger.info(f"  - Users: {len(users)}")
        logger.info(f"  - Files: {len(files)}")
        logger.info(f"  - Documents: {len(documents)}")


@click.command()
@click.option('--clear', is_flag=True, help='Clear database before seeding')
@click.option('--users', default=20, help='Number of users to create')
@click.option('--files', default=100, help='Number of files to create')
@click.option('--documents', default=50, help='Number of documents to create')
def main(clear, users, files, documents):
    """Seed database with test data"""
    
    logger.info("Database Seeding Script")
    logger.info("=" * 50)
    
    # Create database session
    db = SessionLocal()
    seeder = DatabaseSeeder(db)
    
    try:
        if clear:
            seeder.clear_all()
        
        seeder.seed_all(
            users_count=users,
            files_count=files,
            documents_count=documents
        )
        
        logger.info("=" * 50)
        logger.info("✓ Seeding completed successfully!")
        
    except Exception as e:
        logger.error(f"Seeding failed: {e}")
        db.rollback()
        raise
    
    finally:
        db.close()


if __name__ == '__main__':
    main()
2. Test Data Factories
python# tests/factories.py

"""
Test Data Factories

Uses Factory Boy for creating test data
"""

import factory
from factory.alchemy import SQLAlchemyModelFactory
from faker import Faker
from passlib.context import CryptContext

from database import SessionLocal
from models.user import User, Role
from models.file import File
from models.document import Document


# Initialize
fake = Faker(['de_DE'])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class BaseFactory(SQLAlchemyModelFactory):
    """Base factory with database session"""
    
    class Meta:
        abstract = True
        sqlalchemy_session = SessionLocal()
        sqlalchemy_session_persistence = "commit"


class RoleFactory(BaseFactory):
    """Role factory"""
    
    class Meta:
        model = Role
    
    name = factory.Sequence(lambda n: f"role_{n}")
    description = factory.Faker('sentence')
    permissions = factory.List([
        factory.Faker('word') for _ in range(3)
    ])


class UserFactory(BaseFactory):
    """User factory"""
    
    class Meta:
        model = User
    
    email = factory.Faker('email')
    username = factory.Faker('user_name')
    full_name = factory.Faker('name')
    hashed_password = factory.LazyFunction(
        lambda: pwd_context.hash("password123")
    )
    is_active = True
    is_verified = True
    subscription_tier = factory.Faker('random_element', elements=['free', 'pro'])
    role = factory.SubFactory(RoleFactory)


class FileFactory(BaseFactory):
    """File factory"""
    
    class Meta:
        model = File
    
    uuid = factory.Faker('uuid4')
    filename = factory.Faker('file_name')
    original_filename = factory.Faker('file_name')
    storage_type = "local"
    storage_path = factory.Faker('file_path')
    size = factory.Faker('random_int', min=1000, max=1000000)
    mime_type = "application/pdf"
    category = "document"
    user = factory.SubFactory(UserFactory)


class DocumentFactory(BaseFactory):
    """Document factory"""
    
    class Meta:
        model = Document
    
    uuid = factory.Faker('uuid4')
    title = factory.Faker('sentence')
    file = factory.SubFactory(FileFactory)
    user = factory.SubFactory(UserFactory)
    language = "de"
    status = "completed"
    document_type = "invoice"
    ocr_text = factory.Faker('text')
    confidence = 0.95
    page_count = 1


# Usage in tests
def test_user_creation():
    """Example test using factories"""
    user = UserFactory.create()
    assert user.id is not None
    assert user.email is not None


def test_document_with_file():
    """Example test with related objects"""
    document = DocumentFactory.create()
    assert document.file is not None
    assert document.user is not None

🐛 HOT RELOAD & DEBUGGING
1. Advanced Debugging Configuration
python# debug_config.py

"""
Advanced Debugging Configuration

Features:
- Request/Response logging
- SQL query logging
- Performance profiling
- Memory tracking
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import time
from loguru import logger
import tracemalloc
from typing import Callable
import sys


def setup_debug_middleware(app: FastAPI):
    """Setup debugging middleware"""
    
    @app.middleware("http")
    async def debug_middleware(request: Request, call_next: Callable):
        """
        Debug middleware for development
        
        Logs:
        - Request details
        - Response time
        - Memory usage
        """
        
        # Start tracking
        start_time = time.time()
        
        # Memory tracking
        if tracemalloc.is_tracing():
            snapshot_before = tracemalloc.take_snapshot()
        
        # Log request
        logger.debug(
            f"Request: {request.method} {request.url.path}",
            extra={
                "method": request.method,
                "path": request.url.path,
                "query_params": dict(request.query_params),
                "client": request.client.host if request.client else None
            }
        )
        
        # Process request
        try:
            response = await call_next(request)
            
            # Calculate duration
            duration = time.time() - start_time
            
            # Memory diff
            memory_used = None
            if tracemalloc.is_tracing():
                snapshot_after = tracemalloc.take_snapshot()
                top_stats = snapshot_after.compare_to(snapshot_before, 'lineno')
                memory_used = sum(stat.size_diff for stat in top_stats)
            
            # Log response
            logger.debug(
                f"Response: {response.status_code} ({duration*1000:.2f}ms)",
                extra={
                    "status_code": response.status_code,
                    "duration_ms": duration * 1000,
                    "memory_bytes": memory_used
                }
            )
            
            # Add debug headers
            response.headers["X-Process-Time"] = str(duration)
            if memory_used:
                response.headers["X-Memory-Used"] = str(memory_used)
            
            return response
            
        except Exception as e:
            logger.error(f"Request failed: {e}")
            logger.error(traceback.format_exc())
            raise
    
    logger.info("✓ Debug middleware enabled")


def setup_sql_logging():
    """Setup SQL query logging"""
    
    import logging
    
    # SQLAlchemy logging
    logging.basicConfig()
    logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
    
    logger.info("✓ SQL logging enabled")


def setup_memory_profiling():
    """Setup memory profiling"""
    
    tracemalloc.start()
    
    logger.info("✓ Memory profiling enabled")


def setup_development_debugging(app: FastAPI):
    """
    Complete development debugging setup
    
    Call this in main.py when DEBUG=True
    """
    
    logger.info("Setting up development debugging...")
    
    # Middleware
    setup_debug_middleware(app)
    
    # SQL logging
    setup_sql_logging()
    
    # Memory profiling
    setup_memory_profiling()
    
    # Exception handler
    @app.exception_handler(Exception)
    async def debug_exception_handler(request: Request, exc: Exception):
        """Detailed exception handler for debugging"""
        
        import traceback
        
        logger.error(f"Unhandled exception: {exc}")
        logger.error(traceback.format_exc())
        
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal Server Error",
                "message": str(exc),
                "traceback": traceback.format_exc().split('\n'),
                "type": type(exc).__name__
            }
        )
    
    logger.info("✓ Development debugging configured")
2. Hot Reload Configuration
python# hot_reload_config.py

"""
Hot Reload Configuration

Optimized for fast development iteration
"""

import os
from pathlib import Path


# Watchfiles configuration
RELOAD_INCLUDES = [
    "*.py",
    "*.env",
    "*.json",
    "*.yaml",
    "*.toml"
]

RELOAD_EXCLUDES = [
    "venv/*",
    ".venv/*",
    "__pycache__/*",
    "*.pyc",
    ".git/*",
    ".pytest_cache/*",
    ".mypy_cache/*",
    "htmlcov/*"
]

RELOAD_DIRS = [
    ".",
    "backend",
    "config",
    "models",
    "api",
    "services",
    "core"
]


def get_uvicorn_config(debug: bool = True) -> dict:
    """
    Get Uvicorn configuration
    
    Args:
        debug: Enable debug mode
    
    Returns:
        Uvicorn config dict
    """
    
    config = {
        "app": "main:app",
        "host": "0.0.0.0",
        "port": 8000,
        "reload": debug,
        "log_level": "debug" if debug else "info",
        "access_log": debug,
    }
    
    if debug:
        config.update({
            "reload_includes": RELOAD_INCLUDES,
            "reload_excludes": RELOAD_EXCLUDES,
            "reload_dirs": RELOAD_DIRS,
            "use_colors": True,
        })
    
    return config


# Run with:
# uvicorn main:app --reload --reload-include="*.py" --reload-include="*.env"




DEVELOPMENT SETUP & ENVIRONMENT GUIDE - TEIL 3
Git Workflow, Troubleshooting & Best Practices

📋 TABLE OF CONTENTS (TEIL 3)

Git Workflow
Troubleshooting Common Issues
Best Practices Summary
Quick Reference & Checklists


🔀 GIT WORKFLOW
1. Branching Strategy (Git Flow)
bash# .github/BRANCHING_STRATEGY.md

# Git Branching Strategy
# ============================================
#
# We use a modified Git Flow strategy
#
# Branch Types:
# - main       : Production-ready code
# - develop    : Integration branch
# - feature/*  : New features
# - bugfix/*   : Bug fixes
# - hotfix/*   : Critical production fixes
# - release/*  : Release preparation
#
# ============================================

## Branch Structure

main (production)
 │
 ├─ develop (integration)
 │   │
 │   ├─ feature/add-ocr-backend
 │   ├─ feature/improve-ui
 │   └─ bugfix/fix-upload-validation
 │
 └─ hotfix/critical-security-fix


## Branch Naming Convention

feature/TICKET-123-short-description
bugfix/TICKET-456-fix-description
hotfix/critical-issue-description
release/v1.2.0


## Workflow Examples

# ============================================
# 1. Start New Feature
# ============================================

# Update develop
git checkout develop
git pull origin develop

# Create feature branch
git checkout -b feature/OCR-123-add-gpu-backend

# Work on feature...
git add .
git commit -m "feat(ocr): add DeepSeek GPU backend"

# Push to remote
git push -u origin feature/OCR-123-add-gpu-backend

# Create Pull Request on GitHub/GitLab


# ============================================
# 2. Update Feature Branch from Develop
# ============================================

git checkout feature/OCR-123-add-gpu-backend
git fetch origin
git rebase origin/develop

# Or merge if you prefer
# git merge origin/develop


# ============================================
# 3. Complete Feature (Merge to Develop)
# ============================================

# After PR approval
git checkout develop
git pull origin develop
git merge --no-ff feature/OCR-123-add-gpu-backend
git push origin develop

# Delete feature branch
git branch -d feature/OCR-123-add-gpu-backend
git push origin --delete feature/OCR-123-add-gpu-backend


# ============================================
# 4. Create Release
# ============================================

# Create release branch from develop
git checkout develop
git pull origin develop
git checkout -b release/v1.2.0

# Update version numbers
# Update CHANGELOG.md
# Run tests

git add .
git commit -m "chore(release): prepare v1.2.0"

# Merge to main
git checkout main
git merge --no-ff release/v1.2.0
git tag -a v1.2.0 -m "Release v1.2.0"
git push origin main --tags

# Merge back to develop
git checkout develop
git merge --no-ff release/v1.2.0
git push origin develop

# Delete release branch
git branch -d release/v1.2.0


# ============================================
# 5. Hotfix (Critical Production Bug)
# ============================================

# Create from main
git checkout main
git pull origin main
git checkout -b hotfix/critical-security-fix

# Fix the issue
git add .
git commit -m "fix(security): patch critical vulnerability"

# Merge to main
git checkout main
git merge --no-ff hotfix/critical-security-fix
git tag -a v1.2.1 -m "Hotfix v1.2.1"
git push origin main --tags

# Merge to develop
git checkout develop
git merge --no-ff hotfix/critical-security-fix
git push origin develop

# Delete hotfix branch
git branch -d hotfix/critical-security-fix
2. Commit Message Convention
bash# .github/COMMIT_CONVENTION.md

# Commit Message Convention
# ============================================
#
# We follow Conventional Commits specification
# https://www.conventionalcommits.org/
#
# Format:
#   <type>(<scope>): <subject>
#
#   [optional body]
#
#   [optional footer]
#
# ============================================

## Types

feat:     New feature
fix:      Bug fix
docs:     Documentation changes
style:    Code style changes (formatting, etc.)
refactor: Code refactoring
perf:     Performance improvements
test:     Adding or updating tests
build:    Build system changes
ci:       CI/CD changes
chore:    Other changes (dependencies, etc.)
revert:   Revert previous commit


## Scopes

api:      API changes
ocr:      OCR processing
storage:  File storage
auth:     Authentication
db:       Database
ui:       User interface
config:   Configuration


## Examples

# ============================================
# Good Commit Messages
# ============================================

feat(ocr): add DeepSeek GPU backend for complex documents

Implements GPU-accelerated OCR using DeepSeek-Janus-Pro model.
Supports batch processing with configurable batch size.

- Add DeepSeek model integration
- Implement batch processing queue
- Add GPU memory management
- Update configuration options

Closes #123

---

fix(storage): prevent file upload timeout for large files

Increase upload timeout from 30s to 300s and add
chunked upload support for files larger than 100MB.

Fixes #456

---

docs(api): update API documentation for v2 endpoints

- Add examples for new OCR endpoints
- Update authentication section
- Fix typos in response schemas

---

perf(db): optimize database query performance

Add index on frequently queried columns:
- users.email
- files.uuid
- documents.status

Performance improved by ~40% for document listing.

---

# ============================================
# Bad Commit Messages (Avoid!)
# ============================================

# Too vague
update stuff
fix bug
changes

# No type
added new feature
fixed the problem

# Too long subject
feat(ocr): add new GPU backend using DeepSeek model with batch processing support and memory optimization

# Missing scope when needed
feat: add backend
fix: bug
3. Pre-Commit Hooks
yaml# .pre-commit-config.yaml

# Pre-commit Hook Configuration
# ============================================
#
# Install: pre-commit install
# Run manually: pre-commit run --all-files
#
# ============================================

repos:
  # ============================================
  # General Hooks
  # ============================================
  
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      # File checks
      - id: check-added-large-files
        args: ['--maxkb=5000']
      - id: check-case-conflict
      - id: check-merge-conflict
      - id: check-symlinks
      - id: destroyed-symlinks
      
      # JSON/YAML/TOML
      - id: check-json
      - id: check-yaml
      - id: check-toml
      - id: pretty-format-json
        args: ['--autofix', '--no-sort-keys']
      
      # Python
      - id: check-ast
      - id: check-builtin-literals
      - id: check-docstring-first
      - id: debug-statements
      - id: name-tests-test
        args: ['--pytest-test-first']
      
      # Git
      - id: check-vcs-permalinks
      - id: forbid-new-submodules
      
      # Files
      - id: end-of-file-fixer
      - id: trailing-whitespace
      - id: mixed-line-ending
        args: ['--fix=lf']
  
  # ============================================
  # Python Code Quality
  # ============================================
  
  # Black (Code Formatter)
  - repo: https://github.com/psf/black
    rev: 23.12.1
    hooks:
      - id: black
        language_version: python3.11
        args: ['--line-length=100']
  
  # isort (Import Sorting)
  - repo: https://github.com/PyCQA/isort
    rev: 5.13.2
    hooks:
      - id: isort
        args: ['--profile=black', '--line-length=100']
  
  # Ruff (Fast Linter)
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.14
    hooks:
      - id: ruff
        args: ['--fix', '--exit-non-zero-on-fix']
  
  # mypy (Type Checking)
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.8.0
    hooks:
      - id: mypy
        additional_dependencies: [types-all]
        args: ['--ignore-missing-imports', '--strict']
  
  # ============================================
  # Security
  # ============================================
  
  # Bandit (Security Linter)
  - repo: https://github.com/PyCQA/bandit
    rev: 1.7.6
    hooks:
      - id: bandit
        args: ['-r', '.', '-x', './venv,./tests']
  
  # Detect Secrets
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.4.0
    hooks:
      - id: detect-secrets
        args: ['--baseline', '.secrets.baseline']
  
  # ============================================
  # Documentation
  # ============================================
  
  # Markdown
  - repo: https://github.com/executablebooks/mdformat
    rev: 0.7.17
    hooks:
      - id: mdformat
        additional_dependencies:
          - mdformat-gfm
          - mdformat-black
  
  # ============================================
  # Commit Messages
  # ============================================
  
  - repo: https://github.com/compilerla/conventional-pre-commit
    rev: v3.0.0
    hooks:
      - id: conventional-pre-commit
        stages: [commit-msg]
        args: []
  
  # ============================================
  # Git
  # ============================================
  
  # Prevent commits to main/develop
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: no-commit-to-branch
        args: ['--branch=main', '--branch=develop']


# ============================================
# Custom Hook Scripts
# ============================================

  - repo: local
    hooks:
      # Run tests before commit
      - id: pytest-check
        name: pytest-check
        entry: pytest
        language: system
        pass_filenames: false
        always_run: true
        stages: [commit]
        # Only run on manual trigger
        # Remove 'stages' to run on every commit
      
      # Check environment variables
      - id: env-check
        name: env-check
        entry: python scripts/manage_env.py check
        language: system
        pass_filenames: false
        always_run: true
python# scripts/setup_git_hooks.py

"""
Git Hooks Setup Script

Installs custom Git hooks beyond pre-commit
"""

import os
from pathlib import Path
import shutil


HOOKS_DIR = Path(".git/hooks")
SCRIPTS_DIR = Path("scripts/git-hooks")


def install_hook(hook_name: str):
    """Install a Git hook"""
    
    source = SCRIPTS_DIR / hook_name
    target = HOOKS_DIR / hook_name
    
    if not source.exists():
        print(f"⚠ Hook script not found: {source}")
        return
    
    # Copy hook
    shutil.copy(source, target)
    
    # Make executable
    target.chmod(0o755)
    
    print(f"✓ Installed {hook_name}")


def install_all_hooks():
    """Install all Git hooks"""
    
    print("Installing Git hooks...")
    print("=" * 50)
    
    # Create hooks directory if not exists
    HOOKS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Install hooks
    hooks = [
        "pre-commit",
        "commit-msg",
        "pre-push",
        "post-checkout",
        "post-merge"
    ]
    
    for hook in hooks:
        install_hook(hook)
    
    print("=" * 50)
    print("✓ Git hooks installed successfully!")


if __name__ == "__main__":
    install_all_hooks()
bash#!/bin/bash
# scripts/git-hooks/commit-msg
# Commit message validation hook

# ============================================
# COMMIT MESSAGE VALIDATION
# ============================================
#
# Validates commit messages follow convention
#
# ============================================

COMMIT_MSG_FILE=$1
COMMIT_MSG=$(cat "$COMMIT_MSG_FILE")

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Regex for conventional commits
CONVENTIONAL_COMMIT_REGEX='^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([a-z]+\))?: .{1,100}$'

# Check if commit message matches pattern
if ! echo "$COMMIT_MSG" | grep -qE "$CONVENTIONAL_COMMIT_REGEX"; then
    echo -e "${RED}✗ Invalid commit message format${NC}"
    echo ""
    echo "Commit message must follow Conventional Commits:"
    echo ""
    echo -e "${YELLOW}Format:${NC}"
    echo "  <type>(<scope>): <subject>"
    echo ""
    echo -e "${YELLOW}Types:${NC}"
    echo "  feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert"
    echo ""
    echo -e "${YELLOW}Example:${NC}"
    echo "  feat(ocr): add GPU backend support"
    echo "  fix(storage): prevent upload timeout"
    echo "  docs(api): update endpoint documentation"
    echo ""
    echo -e "${YELLOW}Your message:${NC}"
    echo "  $COMMIT_MSG"
    echo ""
    exit 1
fi

# Check subject length
SUBJECT=$(echo "$COMMIT_MSG" | head -1)
if [ ${#SUBJECT} -gt 100 ]; then
    echo -e "${YELLOW}⚠ Commit subject is too long (${#SUBJECT} > 100 chars)${NC}"
    echo "Consider shortening the subject line"
fi

echo -e "${GREEN}✓ Commit message format OK${NC}"
exit 0
bash#!/bin/bash
# scripts/git-hooks/pre-push
# Pre-push validation hook

# ============================================
# PRE-PUSH VALIDATION
# ============================================
#
# Runs before pushing to remote
#
# ============================================

echo "Running pre-push checks..."

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ERRORS=0

# ============================================
# 1. Run Tests
# ============================================

echo ""
echo "Running tests..."

if ! make test-fast; then
    echo -e "${RED}✗ Tests failed${NC}"
    ((ERRORS++))
else
    echo -e "${GREEN}✓ Tests passed${NC}"
fi

# ============================================
# 2. Run Linter
# ============================================

echo ""
echo "Running linter..."

if ! make lint; then
    echo -e "${RED}✗ Linting failed${NC}"
    ((ERRORS++))
else
    echo -e "${GREEN}✓ Linting passed${NC}"
fi

# ============================================
# 3. Check for Debug Code
# ============================================

echo ""
echo "Checking for debug code..."

# Search for common debug patterns
DEBUG_PATTERNS=(
    "import pdb"
    "pdb.set_trace()"
    "breakpoint()"
    "print("
    "console.log("
)

for pattern in "${DEBUG_PATTERNS[@]}"; do
    if git diff --cached | grep -q "$pattern"; then
        echo -e "${YELLOW}⚠ Found debug code: $pattern${NC}"
        echo "  Consider removing before pushing"
    fi
done

# ============================================
# 4. Check for Large Files
# ============================================

echo ""
echo "Checking for large files..."

# Find files > 5MB
LARGE_FILES=$(git diff --cached --name-only | while read file; do
    if [ -f "$file" ]; then
        SIZE=$(stat -f%z "$file" 2>/dev/null || stat -c%s "$file" 2>/dev/null)
        if [ "$SIZE" -gt 5242880 ]; then
            echo "$file ($(numfmt --to=iec-i --suffix=B $SIZE))"
        fi
    fi
done)

if [ -n "$LARGE_FILES" ]; then
    echo -e "${YELLOW}⚠ Large files detected:${NC}"
    echo "$LARGE_FILES"
    echo "Consider using Git LFS for large files"
fi

# ============================================
# Summary
# ============================================

echo ""
echo "=========================================="

if [ $ERRORS -gt 0 ]; then
    echo -e "${RED}✗ Pre-push checks failed with $ERRORS error(s)${NC}"
    echo ""
    echo "Fix the issues and try again, or use --no-verify to skip checks"
    exit 1
else
    echo -e "${GREEN}✓ Pre-push checks passed${NC}"
    exit 0
fi
4. Git Configuration
bash# .gitconfig (Project-specific)

# ============================================
# PROJECT GIT CONFIGURATION
# ============================================
#
# Setup: git config --local include.path ../.gitconfig
#
# ============================================

[core]
    # Editor
    editor = code --wait
    
    # Line endings
    autocrlf = input
    eol = lf
    
    # Performance
    preloadindex = true
    fscache = true

[pull]
    # Rebase on pull
    rebase = true

[push]
    # Push only current branch
    default = current
    
    # Push tags automatically
    followTags = true

[fetch]
    # Prune deleted branches
    prune = true
    pruneTags = true

[merge]
    # Use diff3 for merge conflicts
    conflictstyle = diff3
    
    # Fast-forward only
    ff = only

[rebase]
    # Auto-squash commits marked with squash!/fixup!
    autosquash = true
    
    # Auto-stash before rebase
    autostash = true

[diff]
    # Better diff algorithm
    algorithm = histogram
    
    # Show moved lines
    colorMoved = zebra

[log]
    # Abbreviated commit hashes
    abbrevCommit = true
    
    # Show dates relative
    date = relative

[alias]
    # ============================================
    # Shortcuts
    # ============================================
    
    # Status
    st = status -sb
    
    # Commit
    ci = commit
    amend = commit --amend --no-edit
    fixup = commit --fixup
    
    # Checkout
    co = checkout
    cob = checkout -b
    
    # Branch
    br = branch
    brd = branch -d
    brD = branch -D
    
    # Diff
    df = diff
    dfc = diff --cached
    
    # Log
    lg = log --graph --pretty=format:'%Cred%h%Creset -%C(yellow)%d%Creset %s %Cgreen(%cr) %C(bold blue)<%an>%Creset' --abbrev-commit
    ll = log --oneline --decorate --graph --all
    
    # ============================================
    # Useful Commands
    # ============================================
    
    # Undo last commit (keep changes)
    undo = reset HEAD~1 --mixed
    
    # Undo last commit (discard changes)
    reset-hard = reset HEAD~1 --hard
    
    # Show changed files
    changed = diff --name-only
    
    # Show file history
    filelog = log -u
    
    # Clean merged branches
    cleanup = !git branch --merged | grep -v '\\*\\|main\\|develop' | xargs -n 1 git branch -d
    
    # Pull with rebase
    up = pull --rebase --autostash
    
    # Push force with lease (safer)
    pushf = push --force-with-lease
    
    # Show contributors
    contributors = shortlog --summary --numbered --email
    
    # ============================================
    # Workflow
    # ============================================
    
    # Start new feature
    feature = "!f() { git checkout develop && git pull && git checkout -b feature/$1; }; f"
    
    # Start new bugfix
    bugfix = "!f() { git checkout develop && git pull && git checkout -b bugfix/$1; }; f"
    
    # Start hotfix
    hotfix = "!f() { git checkout main && git pull && git checkout -b hotfix/$1; }; f"
    
    # Finish feature (merge to develop)
    finish = "!f() { BRANCH=$(git branch --show-current); git checkout develop && git pull && git merge --no-ff $BRANCH && git branch -d $BRANCH; }; f"

[color]
    # Enable colors
    ui = auto
    
[color "branch"]
    current = yellow reverse
    local = yellow
    remote = green

[color "diff"]
    meta = yellow bold
    frag = magenta bold
    old = red bold
    new = green bold

[color "status"]
    added = yellow
    changed = green
    untracked = cyan
bash# scripts/setup_git.sh

#!/bin/bash
# Setup Git configuration and hooks

# ============================================
# GIT SETUP SCRIPT
# ============================================

echo "Setting up Git configuration..."

# ============================================
# 1. User Configuration
# ============================================

echo ""
echo "Git User Configuration"
echo "======================"

# Check if user is configured
if ! git config user.name &> /dev/null; then
    read -p "Enter your name: " name
    git config --global user.name "$name"
fi

if ! git config user.email &> /dev/null; then
    read -p "Enter your email: " email
    git config --global user.email "$email"
fi

echo "✓ User: $(git config user.name) <$(git config user.email)>"

# ============================================
# 2. Project Configuration
# ============================================

echo ""
echo "Project Configuration"
echo "====================="

# Include project gitconfig
git config --local include.path ../.gitconfig
echo "✓ Project gitconfig included"

# ============================================
# 3. Install Pre-commit
# ============================================

echo ""
echo "Pre-commit Hooks"
echo "================"

if command -v pre-commit &> /dev/null; then
    pre-commit install
    pre-commit install --hook-type commit-msg
    echo "✓ Pre-commit hooks installed"
else
    echo "⚠ pre-commit not found. Install with: pip install pre-commit"
fi

# ============================================
# 4. Install Custom Hooks
# ============================================

echo ""
echo "Custom Git Hooks"
echo "================"

python scripts/setup_git_hooks.py

# ============================================
# 5. Git LFS (if needed)
# ============================================

echo ""
echo "Git LFS"
echo "======="

if command -v git-lfs &> /dev/null; then
    git lfs install
    echo "✓ Git LFS initialized"
else
    echo "⚠ Git LFS not found (optional)"
    echo "  Install from: https://git-lfs.github.com/"
fi

# ============================================
# Summary
# ============================================

echo ""
echo "=========================================="
echo "✓ Git setup complete!"
echo "=========================================="
echo ""
echo "Useful aliases available:"
echo "  git st       - Status"
echo "  git lg       - Pretty log"
echo "  git feature  - Start new feature"
echo "  git finish   - Merge to develop"
echo ""
echo "Run 'git alias' to see all aliases"

🔧 TROUBLESHOOTING COMMON ISSUES
1. Comprehensive Troubleshooting Guide
markdown# Troubleshooting Guide
# ============================================
# Common issues and solutions
# ============================================

## 🐍 Python Issues

### Issue: ModuleNotFoundError

**Symptom:**
```
ModuleNotFoundError: No module named 'fastapi'
```

**Solutions:**

1. **Virtual environment not activated**
```bash
   # Activate venv
   source venv/bin/activate  # Linux/Mac
   venv\Scripts\activate     # Windows
   
   # Verify
   which python  # Should show venv path
```

2. **Dependencies not installed**
```bash
   pip install -r requirements.txt
```

3. **Wrong Python interpreter in IDE**
   - VS Code: Ctrl+Shift+P → "Python: Select Interpreter"
   - PyCharm: Settings → Project → Python Interpreter


### Issue: ImportError circular dependency

**Symptom:**
```
ImportError: cannot import name 'X' from partially initialized module
```

**Solutions:**

1. **Check import order**
```python
   # ❌ Bad - circular import
   from models.user import User
   from models.file import File  # File imports User
   
   # ✓ Good - import inside function
   def get_user_files(user_id: int):
       from models.file import File
       return File.query.filter_by(user_id=user_id).all()
```

2. **Use TYPE_CHECKING**
```python
   from typing import TYPE_CHECKING
   
   if TYPE_CHECKING:
       from models.user import User
   
   def process_user(user: 'User'):
       pass
```


### Issue: Asyncio RuntimeError

**Symptom:**
```
RuntimeError: asyncio.run() cannot be called from a running event loop
```

**Solution:**
```python
# ❌ Bad
async def main():
    result = asyncio.run(some_async_func())

# ✓ Good
async def main():
    result = await some_async_func()
```


## 🗄️ Database Issues

### Issue: Connection refused

**Symptom:**
```
psycopg2.OperationalError: could not connect to server: Connection refused
```

**Solutions:**

1. **PostgreSQL not running**
```bash
   # Check if PostgreSQL is running
   docker ps  # If using Docker
   sudo systemctl status postgresql  # Linux
   
   # Start PostgreSQL
   docker-compose up -d postgres
   sudo systemctl start postgresql
```

2. **Wrong connection settings**
```bash
   # Check .env
   cat .env | grep POSTGRES
   
   # Test connection
   psql -h localhost -U postgres -d ocr_db
```

3. **Port already in use**
```bash
   # Find process using port 5432
   lsof -i :5432
   sudo netstat -tulpn | grep 5432
   
   # Kill process or change port
```


### Issue: Migration conflicts

**Symptom:**
```
alembic.util.exc.CommandError: Target database is not up to date
```

**Solutions:**

1. **Check migration status**
```bash
   alembic current
   alembic history
```

2. **Reset to specific revision**
```bash
   alembic downgrade 
   alembic upgrade head
```

3. **Nuclear option - reset database**
```bash
   # ⚠️ This deletes all data!
   make db-reset
```


### Issue: Too many connections

**Symptom:**
```
psycopg2.OperationalError: FATAL: sorry, too many clients already
```

**Solutions:**

1. **Check connection pool settings**
```python
   # config/settings.py
   DB_POOL_SIZE = 20  # Reduce if needed
   DB_MAX_OVERFLOW = 10
```

2. **Close unused connections**
```bash
   # PostgreSQL
   SELECT pg_terminate_backend(pid)
   FROM pg_stat_activity
   WHERE state = 'idle'
   AND state_change < NOW() - INTERVAL '10 minutes';
```


## 🐳 Docker Issues

### Issue: Container won't start

**Symptom:**
```
Error response from daemon: driver failed programming external connectivity
```

**Solutions:**

1. **Port already in use**
```bash
   # Find what's using the port
   lsof -i :5432
   
   # Change port in docker-compose.yml
   ports:
     - "5433:5432"  # Map to different host port
```

2. **Container exists with same name**
```bash
   # Remove old container
   docker rm postgres
   
   # Or force remove
   docker rm -f postgres
```


### Issue: Volume permission denied

**Symptom:**
```
Permission denied: '/var/lib/postgresql/data'
```

**Solutions:**

1. **Fix permissions**
```bash
   # Linux
   sudo chown -R $(id -u):$(id -g) ./data
   
   # Or use named volume instead
```

2. **Use named volumes**
```yaml
   # docker-compose.yml
   volumes:
     postgres_data:  # Named volume
   
   services:
     postgres:
       volumes:
         - postgres_data:/var/lib/postgresql/data
```


### Issue: Build cache issues

**Symptom:**
Old dependencies being used after requirements.txt update

**Solutions:**
```bash
# Rebuild without cache
docker-compose build --no-cache

# Or for specific service
docker-compose build --no-cache postgres
```


## 📦 Dependencies Issues

### Issue: Conflicting dependencies

**Symptom:**
```
ERROR: pip's dependency resolver does not currently take into account
all the packages that are installed.
```

**Solutions:**

1. **Create fresh virtual environment**
```bash
   rm -rf venv
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
```

2. **Use pip-tools to resolve**
```bash
   pip install pip-tools
   pip-compile requirements.in
   pip install -r requirements.txt
```


### Issue: SSL Certificate Error

**Symptom:**
```
ssl.SSLError: [SSL: CERTIFICATE_VERIFY_FAILED]
```

**Solutions:**

1. **Update certificates**
```bash
   pip install --upgrade certifi
```

2. **Temporary workaround (not recommended for production)**
```bash
   pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org 
```


## 🔥 Performance Issues

### Issue: Slow startup

**Solutions:**

1. **Profile startup time**
```python
   # Add to main.py
   import time
   start = time.time()
   
   # Your imports and initialization...
   
   print(f"Startup took {time.time() - start:.2f}s")
```

2. **Lazy load heavy modules**
```python
   # ❌ Bad - loads at import
   from heavy_module import something
   
   # ✓ Good - loads when needed
   def use_something():
       from heavy_module import something
       return something()
```


### Issue: High memory usage

**Solutions:**

1. **Profile memory**
```python
   # Use memory_profiler
   pip install memory_profiler
   
   @profile
   def my_function():
       pass
   
   # Run with
   python -m memory_profiler script.py
```

2. **Check for memory leaks**
```python
   import tracemalloc
   
   tracemalloc.start()
   
   # Your code
   
   snapshot = tracemalloc.take_snapshot()
   top_stats = snapshot.statistics('lineno')
   
   for stat in top_stats[:10]:
       print(stat)
```


## 🌐 Network Issues

### Issue: CORS errors

**Symptom:**
```
Access to XMLHttpRequest has been blocked by CORS policy
```

**Solutions:**

1. **Configure CORS in FastAPI**
```python
   # main.py
   from fastapi.middleware.cors import CORSMiddleware
   
   app.add_middleware(
       CORSMiddleware,
       allow_origins=["http://localhost:3000"],
       allow_credentials=True,
       allow_methods=["*"],
       allow_headers=["*"],
   )
```


### Issue: Request timeout

**Solutions:**

1. **Increase timeout**
```python
   # For uvicorn
   uvicorn.run(app, timeout_keep_alive=75)
   
   # For httpx client
   import httpx
   client = httpx.AsyncClient(timeout=30.0)
```


## 🔐 Environment & Config Issues

### Issue: Environment variables not loaded

**Solutions:**

1. **Check .env file**
```bash
   # Verify .env exists
   ls -la .env
   
   # Check contents
   cat .env | grep DATABASE_URL
```

2. **Load .env in code**
```python
   from dotenv import load_dotenv
   load_dotenv()  # Must be called before importing settings
   
   from config import settings
```


### Issue: Secret key warnings

**Symptom:**
```
WARNING: SECRET_KEY must be changed in production
```

**Solutions:**
```bash
# Generate secure secret key
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Add to .env
echo "SECRET_KEY=" >> .env
```


## 🧪 Testing Issues

### Issue: Tests failing in CI but passing locally

**Solutions:**

1. **Check Python version**
```yaml
   # .github/workflows/test.yml
   python-version: '3.11'  # Match local version
```

2. **Install all test dependencies**
```bash
   pip install -r requirements-dev.txt
```

3. **Use same database**
```python
   # tests/conftest.py
   @pytest.fixture
   def db():
       # Use same DB engine as prod
       engine = create_engine(settings.DATABASE_URL)
       ...
```


### Issue: Fixtures not found

**Solution:**
```python
# tests/conftest.py
import pytest

@pytest.fixture
def client():
    # Move fixture to conftest.py
    # to be available across all tests
    pass
```


## 📝 IDE Issues

### Issue: VS Code not finding imports

**Solutions:**

1. **Set Python path**
```json
   // .vscode/settings.json
   {
     "python.analysis.extraPaths": [
       "${workspaceFolder}"
     ]
   }
```

2. **Reload window**
   - Ctrl+Shift+P → "Developer: Reload Window"


### Issue: PyCharm indexing stuck

**Solutions:**

1. **Invalidate caches**
   - File → Invalidate Caches / Restart

2. **Exclude directories**
   - Right-click venv → Mark Directory as → Excluded


## 🚀 Deployment Issues

### Issue: Gunicorn workers dying

**Solutions:**

1. **Increase worker timeout**
```bash
   gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker \
     --timeout 300 \
     --graceful-timeout 300
```

2. **Check worker class**
```bash
   # Use Uvicorn workers for async
   -k uvicorn.workers.UvicornWorker
```
2. Debug Helper Scripts
python# scripts/debug_helper.py

"""
Debug Helper Script

Provides debugging utilities and system checks
"""

import sys
import platform
from pathlib import Path
import subprocess
import psutil
import click


class DebugHelper:
    """System debugging helper"""
    
    @staticmethod
    def system_info():
        """Print system information"""
        
        click.echo("=" * 60)
        click.echo("SYSTEM INFORMATION")
        click.echo("=" * 60)
        
        info = {
            "OS": platform.system(),
            "OS Version": platform.version(),
            "Architecture": platform.machine(),
            "Python Version": sys.version,
            "CPU Count": psutil.cpu_count(),
            "Memory Total": f"{psutil.virtual_memory().total / (1024**3):.2f} GB",
            "Memory Available": f"{psutil.virtual_memory().available / (1024**3):.2f} GB",
            "Disk Usage": f"{psutil.disk_usage('/').percent}%"
        }
        
        for key, value in info.items():
            click.echo(f"{key:20}: {value}")
    
    @staticmethod
    def check_services():
        """Check if required services are running"""
        
        click.echo("\n" + "=" * 60)
        click.echo("SERVICES STATUS")
        click.echo("=" * 60)
        
        services = {
            "PostgreSQL": 5432,
            "Redis": 6379,
            "MinIO": 9000,
            "ClamAV": 3310
        }
        
        for service, port in services.items():
            running = DebugHelper._check_port(port)
            status = "✓ Running" if running else "✗ Not running"
            color = "green" if running else "red"
            click.echo(f"{service:20}: {click.style(status, fg=color)}")
    
    @staticmethod
    def _check_port(port: int) -> bool:
        """Check if port is open"""
        import socket
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('localhost', port))
            sock.close()
            return result == 0
        except:
            return False
    
    @staticmethod
    def check_env():
        """Check environment configuration"""
        
        click.echo("\n" + "=" * 60)
        click.echo("ENVIRONMENT CHECK")
        click.echo("=" * 60)
        
        # Check .env file
        env_file = Path(".env")
        if env_file.exists():
            click.echo(f"✓ .env file exists")
        else:
            click.echo(click.style("✗ .env file missing", fg="red"))
            click.echo("  Run: cp .env.example .env")
        
        # Check virtual environment
        if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
            click.echo("✓ Virtual environment active")
        else:
            click.echo(click.style("✗ Virtual environment not active", fg="yellow"))
            click.echo("  Run: source venv/bin/activate")
        
        # Check key dependencies
        try:
            import fastapi
            click.echo(f"✓ FastAPI installed: {fastapi.__version__}")
        except ImportError:
            click.echo(click.style("✗ FastAPI not installed", fg="red"))
    
    @staticmethod
    def test_database():
        """Test database connection"""
        
        click.echo("\n" + "=" * 60)
        click.echo("DATABASE CONNECTION TEST")
        click.echo("=" * 60)
        
        try:
            from database import engine
            from sqlalchemy import text
            
            with engine.connect() as conn:
                result = conn.execute(text("SELECT version()"))
                version = result.scalar()
                click.echo(f"✓ Connected to PostgreSQL")
                click.echo(f"  Version: {version}")
        except Exception as e:
            click.echo(click.style(f"✗ Database connection failed", fg="red"))
            click.echo(f"  Error: {e}")
    
    @staticmethod
    def test_redis():
        """Test Redis connection"""
        
        click.echo("\n" + "=" * 60)
        click.echo("REDIS CONNECTION TEST")
        click.echo("=" * 60)
        
        try:
            import redis
            from config import settings
            
            r = redis.from_url(settings.REDIS_URL)
            r.ping()
            
            click.echo("✓ Connected to Redis")
            
            # Get info
            info = r.info()
            click.echo(f"  Version: {info['redis_version']}")
            click.echo(f"  Used Memory: {info['used_memory_human']}")
            
        except Exception as e:
            click.echo(click.style("✗ Redis connection failed", fg="red"))
            click.echo(f"  Error: {e}")


@click.group()
def cli():
    """Debug helper utilities"""
    pass


@cli.command()
def info():
    """Show system information"""
    helper = DebugHelper()
    helper.system_info()


@cli.command()
def services():
    """Check services status"""
    helper = DebugHelper()
    helper.check_services()


@cli.command()
def env():
    """Check environment"""
    helper = DebugHelper()
    helper.check_env()


@cli.command()
def db():
    """Test database connection"""
    helper = DebugHelper()
    helper.test_database()


@cli.command()
def redis():
    """Test Redis connection"""
    helper = DebugHelper()
    helper.test_redis()


@cli.command()
def all():
    """Run all checks"""
    helper = DebugHelper()
    helper.system_info()
    helper.check_services()
    helper.check_env()
    helper.test_database()
    helper.test_redis()


if __name__ == '__main__':
    cli()

✅ BEST PRACTICES SUMMARY
Development Best Practices
python# docs/best_practices.py

"""
Development Best Practices Summary
==================================

Comprehensive guide to development best practices
"""

BEST_PRACTICES = {
    # ============================================
    # CODE ORGANIZATION
    # ============================================
    "code_organization": {
        "DO": [
            "Follow consistent project structure",
            "Separate concerns (models, services, API)",
            "Use meaningful file and directory names",
            "Keep files focused and manageable (<500 lines)",
            "Group related functionality together",
            "Use __init__.py for package exports"
        ],
        "DON'T": [
            "Mix business logic with API endpoints",
            "Create god classes/modules",
            "Use vague names like 'utils' or 'helpers'",
            "Nest directories too deeply (>4 levels)",
            "Put everything in one file"
        ]
    },
    
    # ============================================
    # PYTHON CODE STYLE
    # ============================================
    "code_style": {
        "DO": [
            "Follow PEP 8 style guide",
            "Use type hints consistently",
            "Write docstrings for public APIs",
            "Keep line length under 100 characters",
            "Use meaningful variable names",
            "Format code with Black",
            "Sort imports with isort",
            "Use f-strings for formatting"
        ],
        "DON'T": [
            "Use single letter variables (except i, j in loops)",
            "Write long functions (>50 lines)",
            "Ignore type hints",
            "Mix tabs and spaces",
            "Use mutable default arguments",
            "Catch generic exceptions without re-raising"
        ]
    },
    
    # ============================================
    # GIT WORKFLOW
    # ============================================
    "git": {
        "DO": [
            "Write meaningful commit messages",
            "Follow conventional commits",
            "Create feature branches",
            "Keep commits atomic and focused",
            "Pull before pushing",
            "Use .gitignore properly",
            "Review code before merging"
        ],
        "DON'T": [
            "Commit directly to main/develop",
            "Write vague commit messages ('fix', 'update')",
            "Commit large binary files",
            "Push without testing",
            "Commit secrets or credentials",
            "Force push to shared branches"
        ]
    },
    
    # ============================================
    # ENVIRONMENT MANAGEMENT
    # ============================================
    "environment": {
        "DO": [
            "Use virtual environments",
            "Pin dependency versions",
            "Keep .env.example updated",
            "Validate environment variables",
            "Use separate configs for dev/prod",
            "Document required variables"
        ],
        "DON'T": [
            "Install packages globally",
            "Commit .env files",
            "Use default secrets in production",
            "Hardcode configuration",
            "Mix development and production settings"
        ]
    },
    
    # ============================================
    # TESTING
    # ============================================
    "testing": {
        "DO": [
            "Write tests for critical functionality",
            "Use fixtures for test data",
            "Test edge cases and errors",
            "Keep tests fast and isolated",
            "Use meaningful test names",
            "Aim for >80% coverage for critical code"
        ],
        "DON'T": [
            "Skip testing error cases",
            "Write tests that depend on each other",
            "Test implementation details",
            "Use real external services in tests",
            "Ignore failing tests"
        ]
    },
    
    # ============================================
    # DOCUMENTATION
    # ============================================
    "documentation": {
        "DO": [
            "Document public APIs",
            "Keep README.md updated",
            "Add inline comments for complex logic",
            "Document setup procedures",
            "Maintain changelog",
            "Use docstrings for modules/classes/functions"
        ],
        "DON'T": [
            "Write obvious comments",
            "Let documentation get outdated",
            "Over-document simple code",
            "Use comments to explain bad code (refactor instead)"
        ]
    },
    
    # ============================================
    # DEBUGGING
    # ============================================
    "debugging": {
        "DO": [
            "Use debugger instead of print statements",
            "Set up proper logging",
            "Use debug mode in development",
            "Reproduce issues before fixing",
            "Add debug information to errors",
            "Use profiling tools for performance issues"
        ],
        "DON'T": [
            "Leave print() statements in code",
            "Commit breakpoint() calls",
            "Debug in production",
            "Ignore warnings",
            "Fix symptoms instead of root causes"
        ]
    }
}


# Code Quality Checklist
QUALITY_CHECKLIST = """
Before Committing Code:
----------------------

□ Code runs without errors
□ All tests pass
□ No linting errors
□ Type hints added
□ Docstrings written
□ Comments added where needed
□ No debug code (print, breakpoint)
□ No commented-out code
□ Imports organized
□ Code formatted (black, isort)
□ No secrets in code
□ .env.example updated if needed
□ Documentation updated
□ Changelog updated
□ Commit message follows convention

Before Creating PR:
------------------

□ Branch updated from develop
□ All commits squashed/cleaned
□ Tests added for new features
□ No merge conflicts
□ CI passes
□ Code reviewed by yourself
□ Breaking changes documented
□ Migration scripts added if needed

Before Deploying:
----------------

□ All tests pass in CI
□ Code reviewed and approved
□ Database migrations tested
□ Environment variables configured
□ Secrets rotated if needed
□ Rollback plan prepared
□ Monitoring configured
□ Documentation updated
"""

📝 QUICK REFERENCE & CHECKLISTS
Daily Development Workflow
markdown# Daily Development Workflow
# ============================================

## Morning Routine (5 minutes)
```bash
# 1. Pull latest changes
git checkout develop
git pull origin develop

# 2. Start services
make docker-up

# 3. Update dependencies (if needed)
pip install -r requirements.txt

# 4. Run migrations
make migrate

# 5. Start dev server
make dev
```


## Starting New Feature
```bash
# 1. Create feature branch from develop
git checkout develop
git pull
git checkout -b feature/OCR-123-add-feature

# 2. Write code...

# 3. Test locally
make test
make lint

# 4. Commit changes
git add .
git commit -m "feat(ocr): add new feature"

# 5. Push and create PR
git push -u origin feature/OCR-123-add-feature
```


## Before Lunch/End of Day
```bash
# 1. Commit WIP if needed
git add .
git commit -m "wip: work in progress"

# 2. Push to remote (backup)
git push

# 3. Stop services (save resources)
make docker-down
```


## Code Review Checklist

As Reviewer:
- [ ] Code follows project conventions
- [ ] Tests are included and pass
- [ ] No security vulnerabilities
- [ ] Performance considerations addressed
- [ ] Documentation updated
- [ ] No unnecessary complexity

As Author:
- [ ] Self-reviewed code
- [ ] Tested locally
- [ ] Added tests
- [ ] Updated documentation
- [ ] Responded to all comments
Keyboard Shortcuts
markdown# Keyboard Shortcuts Reference
# ============================================

## VS Code

### Navigation
Ctrl+P          - Quick file open
Ctrl+Shift+P    - Command palette
Ctrl+B          - Toggle sidebar
Ctrl+`          - Toggle terminal
Ctrl+Tab        - Switch files

### Editing
Ctrl+D          - Select word (multiple)
Alt+Up/Down     - Move line up/down
Shift+Alt+Up/Down - Copy line up/down
Ctrl+/          - Toggle comment
Ctrl+Shift+K    - Delete line

### Search
Ctrl+F          - Find
Ctrl+H          - Find and replace
Ctrl+Shift+F    - Find in files

### Debug
F5              - Start debugging
F9              - Toggle breakpoint
F10             - Step over
F11             - Step into


## Terminal (Linux/Mac)

### Navigation
Ctrl+A          - Start of line
Ctrl+E          - End of line
Ctrl+U          - Clear line
Ctrl+W          - Delete word
Ctrl+R          - Search history

### Process
Ctrl+C          - Kill process
Ctrl+Z          - Suspend process
Ctrl+D          - Exit shell
```

---

## 🎯 FINAL SUMMARY
```
┌──────────────────────────────────────────────────────────────┐
│     DEVELOPMENT SETUP & ENVIRONMENT - COMPLETE COVERAGE       │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ✅ Local Environment Setup                                  │
│     - Requirements checker                                   │
│     - Automated setup script                                 │
│     - Makefile for task automation                           │
│     - Service orchestration                                  │
│                                                              │
│  ✅ IDE Configuration                                        │
│     - VS Code complete setup                                 │
│     - PyCharm configuration                                  │
│     - Extensions & plugins                                   │
│     - Debug configurations                                   │
│                                                              │
│  ✅ Virtual Environment Setup                                │
│     - venv (built-in)                                        │
│     - pyenv (version management)                             │
│     - Poetry (modern approach)                               │
│     - Dependency management                                  │
│                                                              │
│  ✅ Environment Variables                                    │
│     - Pydantic settings                                      │
│     - .env management                                        │
│     - Multi-environment support                              │
│     - Validation & security                                  │
│                                                              │
│  ✅ Database Seeding                                         │
│     - Complete seeder script                                 │
│     - Faker integration                                      │
│     - Factory pattern                                        │
│     - Test data generation                                   │
│                                                              │
│  ✅ Hot Reload & Debugging                                   │
│     - Advanced debug middleware                              │
│     - SQL logging                                            │
│     - Memory profiling                                       │
│     - Performance tracking                                   │
│                                                              │
│  ✅ Git Workflow                                             │
│     - Branching strategy (Git Flow)                          │
│     - Commit conventions                                     │
│     - Pre-commit hooks                                       │
│     - Custom Git hooks                                       │
│     - Complete aliases                                       │
│                                                              │
│  ✅ Troubleshooting                                          │
│     - Comprehensive guide                                    │
│     - Common issues & solutions                              │
│     - Debug helper scripts                                   │
│     - System diagnostics                                     │
│                                                              │
│  ✅ Best Practices                                           │
│     - Code organization                                      │
│     - Style guidelines                                       │
│     - Testing strategies                                     │
│     - Documentation standards                                │
│                                                              │
│  ✅ Quick Reference                                          │
│     - Daily workflow                                         │
│     - Checklists                                             │
│     - Keyboard shortcuts                                     │
│     - Command reference                                      │
│                                                              │
└──────────────────────────────────────────────────────────────┘