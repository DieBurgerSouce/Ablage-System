#!/bin/bash
# Lint & Format Script - Ablage-System
# Usage: ./scripts/lint.sh [--fix]

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}🔍 Running Code Quality Checks${NC}\n"

FIX=false

if [[ "$1" == "--fix" ]]; then
    FIX=true
    echo -e "${YELLOW}Auto-fix mode enabled${NC}\n"
fi

# 1. Ruff Check
echo -e "${YELLOW}1️⃣  Running Ruff (linter)...${NC}"
if [ "$FIX" = true ]; then
    ruff check . --fix
else
    ruff check .
fi

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Ruff check passed${NC}\n"
else
    echo -e "${RED}❌ Ruff check failed${NC}\n"
    exit 1
fi

# 2. Ruff Format
echo -e "${YELLOW}2️⃣  Running Ruff (formatter)...${NC}"
if [ "$FIX" = true ]; then
    ruff format .
else
    ruff format . --check
fi

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Formatting check passed${NC}\n"
else
    echo -e "${RED}❌ Formatting check failed${NC}"
    echo -e "${YELLOW}Run: ./scripts/lint.sh --fix${NC}\n"
    exit 1
fi

# 3. MyPy Type Check
echo -e "${YELLOW}3️⃣  Running MyPy (type checker)...${NC}"
mypy app/ --strict --ignore-missing-imports

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Type check passed${NC}\n"
else
    echo -e "${RED}❌ Type check failed${NC}\n"
    exit 1
fi

# 4. Import Sort Check
echo -e "${YELLOW}4️⃣  Checking import order...${NC}"
ruff check . --select I

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Import order correct${NC}\n"
else
    echo -e "${RED}❌ Import order incorrect${NC}"
    echo -e "${YELLOW}Run: ./scripts/lint.sh --fix${NC}\n"
    exit 1
fi

# Summary
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ All code quality checks passed!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
