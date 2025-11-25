#!/bin/bash
# Development Server Script - Ablage-System
# Usage: ./scripts/dev.sh

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}🚀 Starting Ablage-System Development Environment${NC}\n"

# 1. Check Prerequisites
echo -e "${YELLOW}1️⃣  Checking prerequisites...${NC}"

# Check Python version
PYTHON_VERSION=$(python --version 2>&1 | awk '{print $2}')
echo -e "  Python: ${GREEN}$PYTHON_VERSION${NC}"

# Check Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker not found${NC}"
    exit 1
fi
echo -e "  Docker: ${GREEN}$(docker --version)${NC}"

# Check GPU
if command -v nvidia-smi &> /dev/null; then
    echo -e "  GPU: ${GREEN}Available${NC}"
else
    echo -e "  GPU: ${YELLOW}Not available (CPU mode)${NC}"
fi

# Check virtual environment
if [[ -z "$VIRTUAL_ENV" ]]; then
    echo -e "\n${YELLOW}⚠️  Virtual environment not activated${NC}"
    echo -e "   Run: source venv/bin/activate"
    exit 1
else
    echo -e "  Virtual Env: ${GREEN}$VIRTUAL_ENV${NC}"
fi

# 2. Start Infrastructure
echo -e "\n${YELLOW}2️⃣  Starting infrastructure...${NC}"

if ! docker ps | grep -q postgres; then
    docker-compose up -d postgres redis minio
    echo -e "  Waiting for services to start..."
    sleep 5
else
    echo -e "  Infrastructure already running"
fi

# 3. Run Migrations
echo -e "\n${YELLOW}3️⃣  Running database migrations...${NC}"
alembic upgrade head

# 4. Start Development Server
echo -e "\n${YELLOW}4️⃣  Starting development server...${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}Server running at: http://localhost:8000${NC}"
echo -e "${GREEN}API docs at: http://localhost:8000/docs${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
