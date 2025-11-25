#!/bin/bash
# Build Script - Ablage-System
# Usage: ./scripts/build.sh [--no-cache]

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}🔨 Building Ablage-System${NC}\n"

NO_CACHE=""

if [[ "$1" == "--no-cache" ]]; then
    NO_CACHE="--no-cache"
    echo -e "${YELLOW}Building without cache${NC}\n"
fi

# 1. Lint & Type Check
echo -e "${YELLOW}1️⃣  Running quality checks...${NC}"
./scripts/lint.sh

# 2. Run Tests
echo -e "\n${YELLOW}2️⃣  Running tests...${NC}"
./scripts/test.sh --cov

# 3. Build Docker Images
echo -e "\n${YELLOW}3️⃣  Building Docker images...${NC}"

echo -e "${BLUE}Building backend image...${NC}"
docker build $NO_CACHE -t ablage-backend:latest -f Dockerfile .

echo -e "${BLUE}Building worker image...${NC}"
docker build $NO_CACHE -t ablage-worker:latest -f docker/Dockerfile.worker .

# 4. Tag images
echo -e "\n${YELLOW}4️⃣  Tagging images...${NC}"
docker tag ablage-backend:latest ablage-backend:$(git rev-parse --short HEAD)
docker tag ablage-worker:latest ablage-worker:$(git rev-parse --short HEAD)

# 5. Summary
echo -e "\n${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ Build completed successfully!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

echo -e "\n${BLUE}Built images:${NC}"
docker images | grep ablage | head -5

echo -e "\n${YELLOW}Next steps:${NC}"
echo -e "  docker-compose up -d"
echo -e "  or"
echo -e "  docker run ablage-backend:latest"
