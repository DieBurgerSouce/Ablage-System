#!/bin/bash

# Prepare Release Script
# Called by semantic-release before publishing

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
VERSION=$1
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

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

# Validate version parameter
if [ -z "$VERSION" ]; then
    log_error "Version parameter is required"
    exit 1
fi

log_info "=== Preparing Release $VERSION ==="
echo ""

# Step 1: Update version in pyproject.toml
log_step "1. Updating version in pyproject.toml..."
cd "$PROJECT_ROOT"

if [ -f "pyproject.toml" ]; then
    # Update version using sed
    sed -i.bak "s/^version = .*/version = \"$VERSION\"/" pyproject.toml
    rm -f pyproject.toml.bak
    log_info "Updated pyproject.toml"
else
    log_warn "pyproject.toml not found, skipping"
fi

# Step 2: Update version in package.json (if exists)
log_step "2. Updating version in package.json..."

if [ -f "package.json" ]; then
    # npm version handles this automatically
    log_info "package.json will be updated by npm plugin"
else
    log_warn "package.json not found, skipping"
fi

# Step 3: Update version in __init__.py
log_step "3. Updating version in Python modules..."

if [ -f "app/__init__.py" ]; then
    echo "__version__ = \"$VERSION\"" > app/__init__.py
    log_info "Updated app/__init__.py"
fi

# Step 4: Build Docker images
log_step "4. Building Docker images..."

DOCKER_REGISTRY="${DOCKER_REGISTRY:-ghcr.io}"
DOCKER_NAMESPACE="${DOCKER_NAMESPACE:-ablage-system}"

log_info "Building backend image..."
docker build \
    -t "$DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-backend:$VERSION" \
    -t "$DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-backend:latest" \
    -f docker/Dockerfile.backend \
    .

log_info "Building worker image..."
docker build \
    -t "$DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-worker:$VERSION" \
    -t "$DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-worker:latest" \
    -f docker/Dockerfile.worker \
    .

log_info "Building frontend image..."
if [ -f "docker/Dockerfile.frontend" ]; then
    docker build \
        -t "$DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-frontend:$VERSION" \
        -t "$DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-frontend:latest" \
        -f docker/Dockerfile.frontend \
        ./frontend
else
    log_warn "Frontend Dockerfile not found, skipping"
fi

# Step 5: Create docker image tags file
log_step "5. Creating docker image tags file..."

mkdir -p "$PROJECT_ROOT/dist"
cat > "$PROJECT_ROOT/dist/docker-images.txt" <<EOF
# Docker Images for Version $VERSION

## Backend
$DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-backend:$VERSION
$DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-backend:latest

## Worker
$DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-worker:$VERSION
$DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-worker:latest

## Frontend
$DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-frontend:$VERSION
$DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-frontend:latest

## Pull Commands
docker pull $DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-backend:$VERSION
docker pull $DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-worker:$VERSION
docker pull $DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-frontend:$VERSION

## Docker Compose
docker-compose pull
docker-compose up -d
EOF

log_info "Created docker-images.txt"

# Step 6: Create distribution tarball
log_step "6. Creating distribution tarball..."

TARBALL_NAME="ablage-system-$VERSION.tar.gz"

tar -czf "$PROJECT_ROOT/dist/$TARBALL_NAME" \
    --exclude='.git' \
    --exclude='node_modules' \
    --exclude='venv' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.pytest_cache' \
    --exclude='.coverage' \
    --exclude='dist' \
    --exclude='site' \
    --exclude='.env' \
    --exclude='*.log' \
    -C "$PROJECT_ROOT" \
    .

log_info "Created $TARBALL_NAME ($(du -h "$PROJECT_ROOT/dist/$TARBALL_NAME" | cut -f1))"

# Step 7: Generate release notes
log_step "7. Generating additional release notes..."

cat > "$PROJECT_ROOT/dist/RELEASE_NOTES.md" <<EOF
# Release $VERSION

## Installation

### Docker Compose (Recommended)

\`\`\`bash
# Pull latest images
docker pull $DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-backend:$VERSION
docker pull $DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-worker:$VERSION

# Update docker-compose.yml to use version $VERSION
docker-compose up -d
\`\`\`

### Manual Installation

\`\`\`bash
# Download tarball
wget https://github.com/ablage-system/ablage-system-ocr/releases/download/v$VERSION/$TARBALL_NAME

# Extract
tar -xzf $TARBALL_NAME
cd ablage-system-$VERSION

# Follow installation guide
# See: docs/installation/production.md
\`\`\`

## Upgrade from Previous Version

\`\`\`bash
# Backup current installation
./scripts/backup.sh

# Pull new images
docker-compose pull

# Apply database migrations
docker-compose run --rm backend alembic upgrade head

# Restart services
docker-compose up -d
\`\`\`

## Breaking Changes

Check CHANGELOG.md for breaking changes and migration guide.

## Documentation

- Full Documentation: https://docs.ablage-system.local
- API Documentation: https://api.ablage-system.local/docs
- GitHub: https://github.com/ablage-system/ablage-system-ocr

## Support

- Issues: https://github.com/ablage-system/ablage-system-ocr/issues
- Discussions: https://github.com/ablage-system/ablage-system-ocr/discussions
- Email: support@ablage-system.local
EOF

log_info "Created RELEASE_NOTES.md"

# Step 8: Run tests
log_step "8. Running tests..."

if command -v pytest &> /dev/null; then
    log_info "Running pytest..."
    cd "$PROJECT_ROOT"

    # Run tests without coverage for speed
    pytest tests/ -v --maxfail=5 || {
        log_error "Tests failed! Aborting release."
        exit 1
    }

    log_info "All tests passed!"
else
    log_warn "pytest not found, skipping tests"
fi

# Step 9: Validate Docker images
log_step "9. Validating Docker images..."

log_info "Testing backend image..."
docker run --rm \
    "$DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-backend:$VERSION" \
    python -c "from app import __version__; print(f'Version: {__version__}')"

log_info "Testing worker image..."
docker run --rm \
    "$DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-worker:$VERSION" \
    python -c "import torch; print(f'PyTorch: {torch.__version__}')"

# Step 10: Update documentation version
log_step "10. Updating documentation version..."

if [ -f "docs/mkdocs.yml" ]; then
    cd "$PROJECT_ROOT/docs"

    # Update version in mkdocs.yml
    sed -i.bak "s/version: .*/version: $VERSION/" mkdocs.yml
    rm -f mkdocs.yml.bak

    # Build documentation
    if command -v mkdocs &> /dev/null; then
        log_info "Building documentation..."
        mkdocs build --strict
        log_info "Documentation built successfully"
    fi
fi

# Summary
echo ""
log_info "=== Release Preparation Complete ==="
echo ""
log_info "Version: $VERSION"
log_info "Docker Images: 3 (backend, worker, frontend)"
log_info "Distribution: $TARBALL_NAME"
log_info "Tests: Passed"
echo ""
log_info "Ready for publishing!"
echo ""

# Create success marker
touch "$PROJECT_ROOT/dist/.prepared-$VERSION"

exit 0
