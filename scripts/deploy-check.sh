#!/bin/bash
# Pre-Deployment Validation Script - Ablage-System OCR
# Comprehensive checks before deploying to production

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
DOCKER_COMPOSE="docker-compose -f docker-compose.yml -f docker-compose.dev.yml"
CHECKS_PASSED=0
CHECKS_FAILED=0
CHECKS_WARNINGS=0

# Function to report check result
report_check() {
    local status=$1
    local message=$2

    if [ "$status" == "pass" ]; then
        echo -e "${GREEN}✅ PASS:${NC} $message"
        CHECKS_PASSED=$((CHECKS_PASSED + 1))
    elif [ "$status" == "fail" ]; then
        echo -e "${RED}❌ FAIL:${NC} $message"
        CHECKS_FAILED=$((CHECKS_FAILED + 1))
    elif [ "$status" == "warn" ]; then
        echo -e "${YELLOW}⚠️  WARN:${NC} $message"
        CHECKS_WARNINGS=$((CHECKS_WARNINGS + 1))
    fi
}

# Check 1: Git repository is clean
check_git_clean() {
    echo -e "${BLUE}📋 Checking Git repository status...${NC}"

    if [ ! -d ".git" ]; then
        report_check "warn" "Not a Git repository"
        return
    fi

    if [ -z "$(git status --porcelain)" ]; then
        report_check "pass" "Git repository is clean"
    else
        report_check "fail" "Git repository has uncommitted changes"
        git status --short
    fi
}

# Check 2: All tests pass
check_tests() {
    echo -e "${BLUE}🧪 Running tests...${NC}"

    if command -v pytest &> /dev/null; then
        if pytest tests/ -q --tb=no > /dev/null 2>&1; then
            report_check "pass" "All tests passed"
        else
            report_check "fail" "Some tests failed"
            echo -e "${YELLOW}   Run 'make test' for details${NC}"
        fi
    else
        report_check "warn" "pytest not found - skipping tests"
    fi
}

# Check 3: Code quality (linting)
check_linting() {
    echo -e "${BLUE}🔍 Checking code quality...${NC}"

    if command -v ruff &> /dev/null; then
        if ruff check . --quiet > /dev/null 2>&1; then
            report_check "pass" "No linting errors"
        else
            report_check "fail" "Linting errors found"
            echo -e "${YELLOW}   Run 'make lint' for details${NC}"
        fi
    else
        report_check "warn" "Ruff not found - skipping linting"
    fi
}

# Check 4: Type checking
check_types() {
    echo -e "${BLUE}🔤 Checking type annotations...${NC}"

    if command -v mypy &> /dev/null; then
        if mypy app/ --quiet > /dev/null 2>&1; then
            report_check "pass" "Type checking passed"
        else
            report_check "fail" "Type checking errors"
            echo -e "${YELLOW}   Run 'mypy app/' for details${NC}"
        fi
    else
        report_check "warn" "MyPy not found - skipping type checking"
    fi
}

# Check 5: Security scan
check_security() {
    echo -e "${BLUE}🔒 Running security scan...${NC}"

    if command -v bandit &> /dev/null; then
        if bandit -r app/ -q -f screen > /dev/null 2>&1; then
            report_check "pass" "No security issues found"
        else
            report_check "warn" "Security issues detected"
            echo -e "${YELLOW}   Run 'bandit -r app/' for details${NC}"
        fi
    else
        report_check "warn" "Bandit not found - skipping security scan"
    fi
}

# Check 6: Dependencies up to date
check_dependencies() {
    echo -e "${BLUE}📦 Checking dependencies...${NC}"

    if [ -f "requirements.txt" ]; then
        # Check for known vulnerabilities
        if command -v safety &> /dev/null; then
            if safety check -r requirements.txt --json > /dev/null 2>&1; then
                report_check "pass" "No known vulnerabilities in dependencies"
            else
                report_check "warn" "Some dependencies have known vulnerabilities"
                echo -e "${YELLOW}   Run 'safety check' for details${NC}"
            fi
        else
            report_check "warn" "Safety not found - skipping vulnerability check"
        fi
    else
        report_check "warn" "requirements.txt not found"
    fi
}

# Check 7: Database migrations
check_migrations() {
    echo -e "${BLUE}🗄️  Checking database migrations...${NC}"

    if [ -d "migrations/versions" ]; then
        PENDING_MIGRATIONS=$(find migrations/versions -name "*.py" -newer .last-deploy 2>/dev/null | wc -l)

        if [ "$PENDING_MIGRATIONS" -gt 0 ]; then
            report_check "warn" "$PENDING_MIGRATIONS new migration(s) since last deployment"
            echo -e "${YELLOW}   Ensure migrations are tested before deploying${NC}"
        else
            report_check "pass" "No new migrations since last deployment"
        fi
    else
        report_check "warn" "No migrations directory found"
    fi
}

# Check 8: Environment variables
check_environment() {
    echo -e "${BLUE}🔧 Checking environment configuration...${NC}"

    if [ ! -f ".env.example" ]; then
        report_check "warn" ".env.example not found"
        return
    fi

    # Check if all required env vars from .env.example are set
    MISSING_VARS=0
    while IFS= read -r line; do
        # Skip comments and empty lines
        [[ $line =~ ^#.*$ ]] && continue
        [[ -z "$line" ]] && continue

        VAR_NAME=$(echo "$line" | cut -d= -f1)

        if [ -z "${!VAR_NAME}" ]; then
            MISSING_VARS=$((MISSING_VARS + 1))
        fi
    done < .env.example

    if [ "$MISSING_VARS" -eq 0 ]; then
        report_check "pass" "All required environment variables are set"
    else
        report_check "warn" "$MISSING_VARS environment variable(s) not set"
        echo -e "${YELLOW}   Check .env.example for required variables${NC}"
    fi
}

# Check 9: Docker images build successfully
check_docker_build() {
    echo -e "${BLUE}🐳 Checking Docker build...${NC}"

    if [ -f "docker-compose.yml" ]; then
        if docker-compose -f docker-compose.yml config > /dev/null 2>&1; then
            report_check "pass" "Docker Compose configuration is valid"
        else
            report_check "fail" "Docker Compose configuration has errors"
        fi
    else
        report_check "warn" "docker-compose.yml not found"
    fi
}

# Check 10: VERSION file exists and is valid
check_version() {
    echo -e "${BLUE}📌 Checking version...${NC}"

    if [ -f "VERSION" ]; then
        VERSION=$(cat VERSION | tr -d '\n')

        if [[ $VERSION =~ ^[0-9]+\.[0-9]+\.[0-9]+(-dev)?$ ]]; then
            report_check "pass" "Version: $VERSION"

            if [[ $VERSION == *"-dev"* ]]; then
                report_check "warn" "Deploying development version"
            fi
        else
            report_check "fail" "Invalid version format: $VERSION"
        fi
    else
        report_check "fail" "VERSION file not found"
    fi
}

# Check 11: Critical files exist
check_critical_files() {
    echo -e "${BLUE}📁 Checking critical files...${NC}"

    CRITICAL_FILES=(
        "app/main.py"
        "requirements.txt"
        "docker-compose.yml"
        "Makefile"
    )

    MISSING_FILES=0
    for file in "${CRITICAL_FILES[@]}"; do
        if [ ! -f "$file" ]; then
            report_check "fail" "Missing critical file: $file"
            MISSING_FILES=$((MISSING_FILES + 1))
        fi
    done

    if [ "$MISSING_FILES" -eq 0 ]; then
        report_check "pass" "All critical files present"
    fi
}

# Check 12: Backup exists
check_backup() {
    echo -e "${BLUE}💾 Checking backup status...${NC}"

    if [ -d "backups" ]; then
        LATEST_BACKUP=$(ls -t backups/backup_*.tar.gz 2>/dev/null | head -1)

        if [ -n "$LATEST_BACKUP" ]; then
            BACKUP_AGE=$(( ($(date +%s) - $(stat -c %Y "$LATEST_BACKUP" 2>/dev/null || stat -f %m "$LATEST_BACKUP")) / 86400 ))
            report_check "pass" "Latest backup: $LATEST_BACKUP ($BACKUP_AGE days old)"

            if [ "$BACKUP_AGE" -gt 7 ]; then
                report_check "warn" "Backup is older than 7 days"
            fi
        else
            report_check "warn" "No backups found"
        fi
    else
        report_check "warn" "Backups directory not found"
    fi
}

# Check 13: Documentation is up to date
check_documentation() {
    echo -e "${BLUE}📚 Checking documentation...${NC}"

    DOCS_FILES=("README.md" "CLAUDE.md")
    MISSING_DOCS=0

    for doc in "${DOCS_FILES[@]}"; do
        if [ ! -f "$doc" ]; then
            MISSING_DOCS=$((MISSING_DOCS + 1))
        fi
    done

    if [ "$MISSING_DOCS" -eq 0 ]; then
        report_check "pass" "Documentation files present"
    else
        report_check "warn" "$MISSING_DOCS documentation file(s) missing"
    fi
}

# Check 14: Disk space
check_disk_space() {
    echo -e "${BLUE}💽 Checking disk space...${NC}"

    AVAILABLE_SPACE=$(df -h . | awk 'NR==2 {print $4}')
    AVAILABLE_SPACE_GB=$(df -BG . | awk 'NR==2 {print $4}' | sed 's/G//')

    if [ "$AVAILABLE_SPACE_GB" -gt 10 ]; then
        report_check "pass" "Sufficient disk space: $AVAILABLE_SPACE available"
    else
        report_check "warn" "Low disk space: $AVAILABLE_SPACE available"
    fi
}

# Check 15: Network connectivity
check_network() {
    echo -e "${BLUE}🌐 Checking network connectivity...${NC}"

    # Check if we can reach package registries
    if curl -s --connect-timeout 5 https://pypi.org > /dev/null 2>&1; then
        report_check "pass" "PyPI reachable"
    else
        report_check "warn" "Cannot reach PyPI"
    fi

    if curl -s --connect-timeout 5 https://hub.docker.com > /dev/null 2>&1; then
        report_check "pass" "Docker Hub reachable"
    else
        report_check "warn" "Cannot reach Docker Hub"
    fi
}

# Generate summary report
generate_summary() {
    echo ""
    echo -e "${BLUE}════════════════════════════════════════${NC}"
    echo -e "${BLUE}   Pre-Deployment Check Summary${NC}"
    echo -e "${BLUE}════════════════════════════════════════${NC}"
    echo ""
    echo -e "${GREEN}✅ Passed:${NC}   $CHECKS_PASSED"
    echo -e "${YELLOW}⚠️  Warnings:${NC} $CHECKS_WARNINGS"
    echo -e "${RED}❌ Failed:${NC}   $CHECKS_FAILED"
    echo ""

    if [ "$CHECKS_FAILED" -eq 0 ]; then
        if [ "$CHECKS_WARNINGS" -eq 0 ]; then
            echo -e "${GREEN}🎉 All checks passed! Ready to deploy.${NC}"
            return 0
        else
            echo -e "${YELLOW}⚠️  Deployment possible with warnings.${NC}"
            echo -e "${YELLOW}   Review warnings before proceeding.${NC}"
            return 0
        fi
    else
        echo -e "${RED}❌ Deployment NOT recommended!${NC}"
        echo -e "${RED}   Fix failed checks before deploying.${NC}"
        return 1
    fi
}

# Main script
main() {
    echo -e "${BLUE}🔍 Pre-Deployment Validation Script${NC}"
    echo -e "${BLUE}════════════════════════════════════${NC}"
    echo ""

    # Run all checks
    check_git_clean
    check_tests
    check_linting
    check_types
    check_security
    check_dependencies
    check_migrations
    check_environment
    check_docker_build
    check_version
    check_critical_files
    check_backup
    check_documentation
    check_disk_space
    check_network

    # Generate summary
    generate_summary
    EXIT_CODE=$?

    # Touch marker file for migration check
    touch .last-deploy

    exit $EXIT_CODE
}

# Run main function
main
