#!/bin/bash

# MkDocs Development Server
# Serves documentation locally with hot-reload

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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
    log_info "Installing/updating dependencies..."
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

# Serve documentation
serve_docs() {
    log_info "Starting MkDocs development server..."
    log_info "Documentation will be available at: http://127.0.0.1:8000"
    log_info "Press Ctrl+C to stop the server"
    echo ""

    cd "$SCRIPT_DIR"
    mkdocs serve --dev-addr=127.0.0.1:8000
}

# Main function
main() {
    echo ""
    log_info "=== MkDocs Development Server ==="
    echo ""

    check_python
    check_venv
    activate_venv
    check_dependencies
    serve_docs
}

# Run main function
main "$@"
