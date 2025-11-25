#!/bin/bash
# DevContainer Post-Create Setup Script
# Runs automatically after the container is created

set -e

echo "🚀 Starting Ablage-System DevContainer setup..."

# Color output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Change to workspace directory
cd /workspace

# 1. Install Python dependencies
echo -e "${BLUE}📦 Installing Python dependencies...${NC}"
if [ -f "requirements.txt" ]; then
    pip install --no-cache-dir -r requirements.txt
    echo -e "${GREEN}✓ Requirements installed${NC}"
else
    echo -e "${YELLOW}⚠ requirements.txt not found, skipping${NC}"
fi

if [ -f "requirements-dev.txt" ]; then
    pip install --no-cache-dir -r requirements-dev.txt
    echo -e "${GREEN}✓ Dev requirements installed${NC}"
else
    echo -e "${YELLOW}⚠ requirements-dev.txt not found, skipping${NC}"
fi

# 2. Set up pre-commit hooks
echo -e "${BLUE}🪝 Setting up pre-commit hooks...${NC}"
if [ -f ".pre-commit-config.yaml" ]; then
    pre-commit install --install-hooks
    pre-commit install --hook-type commit-msg
    echo -e "${GREEN}✓ Pre-commit hooks installed${NC}"
else
    echo -e "${YELLOW}⚠ .pre-commit-config.yaml not found, skipping${NC}"
fi

# 3. Configure Git
echo -e "${BLUE}🔧 Configuring Git...${NC}"
git config --global --add safe.directory /workspace
git config --global core.autocrlf input
git config --global core.eol lf
git config --global pull.rebase false
echo -e "${GREEN}✓ Git configured${NC}"

# 4. Create necessary directories
echo -e "${BLUE}📁 Creating project directories...${NC}"
mkdir -p logs
mkdir -p data/uploads
mkdir -p data/processed
mkdir -p data/exports
mkdir -p .pytest_cache
mkdir -p .mypy_cache
mkdir -p .ruff_cache
echo -e "${GREEN}✓ Directories created${NC}"

# 5. Wait for database to be ready
echo -e "${BLUE}🗄️  Waiting for PostgreSQL...${NC}"
max_attempts=30
attempt=0
until PGPASSWORD=postgres psql -h postgres -U postgres -d ablage_ocr -c '\q' 2>/dev/null; do
    attempt=$((attempt + 1))
    if [ $attempt -eq $max_attempts ]; then
        echo -e "${YELLOW}⚠ PostgreSQL not ready after ${max_attempts} attempts${NC}"
        break
    fi
    echo "Waiting for PostgreSQL... (attempt $attempt/$max_attempts)"
    sleep 2
done

if [ $attempt -lt $max_attempts ]; then
    echo -e "${GREEN}✓ PostgreSQL is ready${NC}"

    # 6. Run database migrations
    echo -e "${BLUE}🔄 Running database migrations...${NC}"
    if [ -d "migrations" ] && [ -f "alembic.ini" ]; then
        alembic upgrade head || echo -e "${YELLOW}⚠ Migrations failed or none to apply${NC}"
        echo -e "${GREEN}✓ Migrations applied${NC}"
    else
        echo -e "${YELLOW}⚠ No Alembic configuration found, skipping migrations${NC}"
    fi
fi

# 7. Wait for Redis
echo -e "${BLUE}🔴 Waiting for Redis...${NC}"
max_attempts=15
attempt=0
until redis-cli -h redis ping 2>/dev/null | grep -q PONG; do
    attempt=$((attempt + 1))
    if [ $attempt -eq $max_attempts ]; then
        echo -e "${YELLOW}⚠ Redis not ready after ${max_attempts} attempts${NC}"
        break
    fi
    echo "Waiting for Redis... (attempt $attempt/$max_attempts)"
    sleep 2
done

if [ $attempt -lt $max_attempts ]; then
    echo -e "${GREEN}✓ Redis is ready${NC}"
fi

# 8. Wait for MinIO
echo -e "${BLUE}🗄️  Waiting for MinIO...${NC}"
max_attempts=15
attempt=0
until curl -sf http://minio:9000/minio/health/live > /dev/null 2>&1; do
    attempt=$((attempt + 1))
    if [ $attempt -eq $max_attempts ]; then
        echo -e "${YELLOW}⚠ MinIO not ready after ${max_attempts} attempts${NC}"
        break
    fi
    echo "Waiting for MinIO... (attempt $attempt/$max_attempts)"
    sleep 2
done

if [ $attempt -lt $max_attempts ]; then
    echo -e "${GREEN}✓ MinIO is ready${NC}"
fi

# 9. Check GPU availability
echo -e "${BLUE}🎮 Checking GPU availability...${NC}"
if command -v nvidia-smi &> /dev/null; then
    nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader

    # Check CUDA availability in Python
    if python -c "import torch; assert torch.cuda.is_available()" 2>/dev/null; then
        GPU_NAME=$(python -c "import torch; print(torch.cuda.get_device_name(0))")
        echo -e "${GREEN}✓ GPU available: ${GPU_NAME}${NC}"
    else
        echo -e "${YELLOW}⚠ CUDA not available in Python${NC}"
    fi
else
    echo -e "${YELLOW}⚠ nvidia-smi not found${NC}"
fi

# 10. Create .env file if it doesn't exist
echo -e "${BLUE}⚙️  Setting up environment file...${NC}"
if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    cp .env.example .env
    echo -e "${GREEN}✓ Created .env from .env.example${NC}"
    echo -e "${YELLOW}⚠ Please review and update .env with your settings${NC}"
elif [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠ No .env or .env.example found${NC}"
else
    echo -e "${GREEN}✓ .env already exists${NC}"
fi

# 11. Install Node.js dependencies if package.json exists (for future frontend)
if [ -f "package.json" ]; then
    echo -e "${BLUE}📦 Installing Node.js dependencies...${NC}"
    npm install
    echo -e "${GREEN}✓ Node.js dependencies installed${NC}"
fi

# 12. Set proper permissions
echo -e "${BLUE}🔒 Setting permissions...${NC}"
sudo chown -R vscode:vscode /workspace/.git 2>/dev/null || true
sudo chown -R vscode:vscode /workspace/logs 2>/dev/null || true
sudo chown -R vscode:vscode /workspace/data 2>/dev/null || true
echo -e "${GREEN}✓ Permissions set${NC}"

# 13. Display helpful information
echo ""
echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✨ Ablage-System DevContainer setup complete!${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${BLUE}📊 Available Services:${NC}"
echo "  - FastAPI API:        http://localhost:8000"
echo "  - API Docs (Swagger): http://localhost:8000/docs"
echo "  - PostgreSQL:         localhost:5432"
echo "  - Redis:              localhost:6379"
echo "  - MinIO API:          http://localhost:9000"
echo "  - MinIO Console:      http://localhost:9001"
echo "  - pgAdmin:            http://localhost:5050"
echo "  - Redis Commander:    http://localhost:8081"
echo ""
echo -e "${BLUE}🚀 Quick Commands:${NC}"
echo "  Start API:            uvicorn app.main:app --reload --host 0.0.0.0"
echo "  Run tests:            pytest"
echo "  Run with coverage:    pytest --cov=app --cov-report=html"
echo "  Lint code:            ruff check ."
echo "  Format code:          ruff format ."
echo "  Type check:           mypy app/"
echo "  Run migrations:       alembic upgrade head"
echo "  Check GPU:            nvidia-smi"
echo ""
echo -e "${BLUE}📚 Documentation:${NC}"
echo "  Main instructions:    cat CLAUDE.md"
echo "  Quick reference:      cat .claude/quick-reference/claude-code-essentials.md"
echo "  Architecture:         cat ARCHITECTURE.md (if exists)"
echo ""
echo -e "${YELLOW}💡 Tip: Use VSCode tasks (Ctrl+Shift+P → 'Tasks: Run Task') for common operations${NC}"
echo ""
