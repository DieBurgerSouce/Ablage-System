#!/bin/bash
# Test Runner Script - Ablage-System
# Usage: ./scripts/test.sh [options]

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🧪 Running Ablage-System Test Suite${NC}\n"

# Parse arguments
COVERAGE=false
VERBOSE=false
MARKERS=""
PARALLEL=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --cov|--coverage)
            COVERAGE=true
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        --gpu)
            MARKERS="gpu"
            shift
            ;;
        --no-gpu)
            MARKERS="not gpu"
            shift
            ;;
        --unit)
            MARKERS="unit"
            shift
            ;;
        --integration)
            MARKERS="integration"
            shift
            ;;
        --parallel)
            PARALLEL=true
            shift
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# Build pytest command
CMD="pytest"

if [ "$VERBOSE" = true ]; then
    CMD="$CMD -v"
fi

if [ "$COVERAGE" = true ]; then
    CMD="$CMD --cov=app --cov-report=term-missing --cov-report=html"
fi

if [ -n "$MARKERS" ]; then
    CMD="$CMD -m \"$MARKERS\""
fi

if [ "$PARALLEL" = true ]; then
    CMD="$CMD -n auto"
fi

# Add default flags
CMD="$CMD --tb=short --strict-markers"

# Run tests
echo -e "${YELLOW}Command: $CMD${NC}\n"
eval $CMD

# Check exit code
if [ $? -eq 0 ]; then
    echo -e "\n${GREEN}✅ All tests passed!${NC}"

    if [ "$COVERAGE" = true ]; then
        echo -e "${YELLOW}📊 Coverage report: htmlcov/index.html${NC}"
    fi
else
    echo -e "\n${RED}❌ Tests failed!${NC}"
    exit 1
fi
