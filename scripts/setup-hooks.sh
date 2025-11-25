#!/bin/bash
# Setup Git Hooks - Ablage-System
# Configures Git to use hooks from .githooks/ directory

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}🔧 Setting up Git hooks...${NC}\n"

# Check if we're in a git repository
if [ ! -d ".git" ]; then
    echo -e "${RED}❌ Error: Not in a git repository${NC}"
    exit 1
fi

# Configure Git to use .githooks directory
echo -e "${YELLOW}Configuring Git hooks directory...${NC}"
git config core.hooksPath .githooks

# Make hooks executable (Unix-like systems)
if [ -d ".githooks" ]; then
    echo -e "${YELLOW}Making hooks executable...${NC}"
    chmod +x .githooks/* 2>/dev/null || true
fi

# Verify hooks are set up
echo -e "\n${GREEN}✅ Git hooks configured!${NC}"
echo -e "${GREEN}Hooks directory: .githooks/${NC}\n"

# List installed hooks
echo -e "${YELLOW}Installed hooks:${NC}"
if [ -d ".githooks" ]; then
    for hook in .githooks/*; do
        if [ -f "$hook" ] && [ -x "$hook" ]; then
            hook_name=$(basename "$hook")
            echo -e "  ${GREEN}✓${NC} $hook_name"
        fi
    done
else
    echo -e "  ${YELLOW}No hooks found${NC}"
fi

echo -e "\n${YELLOW}Pre-commit hook will run:${NC}"
echo "  - Ruff linting"
echo "  - Code formatting check"
echo "  - MyPy type checking"
echo "  - Debugging code detection"
echo "  - Secret scanning"
echo "  - File size check"

echo -e "\n${YELLOW}Pre-push hook will run:${NC}"
echo "  - Quick lint check"
echo "  - Type checking"
echo "  - Unit tests"
echo "  - Coverage check (warning only)"
echo "  - Merge conflict detection"
echo "  - Large file detection"
echo "  - Branch protection for main/master"

echo -e "\n${GREEN}🎉 Setup complete!${NC}"
echo -e "${YELLOW}Note: Hooks will run automatically on commit and push${NC}"
echo -e "${YELLOW}To skip hooks temporarily, use: git commit --no-verify${NC}"

exit 0
