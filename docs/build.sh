#!/bin/bash

# MkDocs Build Script
# Builds static documentation site

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/site"

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

# Check if Python is installed
check_python() {
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 is not installed"
        exit 1
    fi

    local python_version=$(python3 --version 2>&1 | awk '{print $2}')
    log_info "Using Python $python_version"
}

# Check if virtual environment exists
check_venv() {
    if [ ! -d "$SCRIPT_DIR/venv" ]; then
        log_warn "Virtual environment not found. Creating..."
        python3 -m venv "$SCRIPT_DIR/venv"
    fi
}

# Activate virtual environment
activate_venv() {
    log_info "Activating virtual environment..."

    if [ -f "$SCRIPT_DIR/venv/bin/activate" ]; then
        # shellcheck disable=SC1091
        source "$SCRIPT_DIR/venv/bin/activate"
    elif [ -f "$SCRIPT_DIR/venv/Scripts/activate" ]; then
        # shellcheck disable=SC1091
        source "$SCRIPT_DIR/venv/Scripts/activate"
    else
        log_error "Cannot find virtual environment activation script"
        exit 1
    fi
}

# Install dependencies
install_dependencies() {
    log_step "Installing/updating dependencies..."
    pip install --upgrade pip > /dev/null 2>&1
    pip install -r "$SCRIPT_DIR/requirements.txt" > /dev/null 2>&1
    log_info "Dependencies installed"
}

# Check if dependencies are installed
check_dependencies() {
    if ! python -c "import mkdocs" 2>/dev/null; then
        log_warn "MkDocs not found. Installing dependencies..."
        install_dependencies
    fi
}

# Clean previous build
clean_build() {
    if [ -d "$BUILD_DIR" ]; then
        log_step "Cleaning previous build..."
        rm -rf "$BUILD_DIR"
        log_info "Previous build cleaned"
    fi
}

# Validate mkdocs.yml
validate_config() {
    log_step "Validating mkdocs.yml..."

    if [ ! -f "$SCRIPT_DIR/mkdocs.yml" ]; then
        log_error "mkdocs.yml not found"
        exit 1
    fi

    # Check for syntax errors
    if ! python -c "import yaml; yaml.safe_load(open('$SCRIPT_DIR/mkdocs.yml'))" 2>/dev/null; then
        log_error "Invalid mkdocs.yml syntax"
        exit 1
    fi

    log_info "Configuration valid"
}

# Build documentation
build_docs() {
    log_step "Building documentation..."

    cd "$SCRIPT_DIR"

    if mkdocs build --strict --verbose; then
        log_info "Build successful!"
    else
        log_error "Build failed"
        exit 1
    fi
}

# Calculate build size
calculate_size() {
    if [ -d "$BUILD_DIR" ]; then
        local size=$(du -sh "$BUILD_DIR" | cut -f1)
        log_info "Build size: $size"

        local file_count=$(find "$BUILD_DIR" -type f | wc -l)
        log_info "Total files: $file_count"
    fi
}

# Show build info
show_build_info() {
    echo ""
    log_info "=== Build Information ==="
    log_info "Build directory: $BUILD_DIR"
    log_info "Built at: $(date '+%Y-%m-%d %H:%M:%S')"
    calculate_size
    echo ""
    log_info "To serve locally: cd $SCRIPT_DIR && python -m http.server --directory site 8000"
    log_info "Or use: ./serve.sh"
    echo ""
}

# Deploy to GitHub Pages (optional)
deploy_github_pages() {
    if [ "$1" == "--deploy" ]; then
        log_step "Deploying to GitHub Pages..."

        if ! command -v git &> /dev/null; then
            log_error "Git is not installed"
            exit 1
        fi

        cd "$SCRIPT_DIR"
        mkdocs gh-deploy --force

        log_info "Deployed to GitHub Pages"
    fi
}

# Main function
main() {
    echo ""
    log_info "=== MkDocs Build Script ==="
    echo ""

    check_python
    check_venv
    activate_venv
    check_dependencies
    validate_config
    clean_build
    build_docs
    show_build_info
    deploy_github_pages "$@"
}

# Help message
show_help() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --deploy    Deploy to GitHub Pages after build"
    echo "  --help      Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0              Build documentation"
    echo "  $0 --deploy     Build and deploy to GitHub Pages"
    echo ""
}

# Parse arguments
if [ "$1" == "--help" ]; then
    show_help
    exit 0
fi

# Run main function
main "$@"
