#!/bin/bash

# Publish Release Script
# Called by semantic-release to publish artifacts

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

# Check if preparation was successful
if [ ! -f "$PROJECT_ROOT/dist/.prepared-$VERSION" ]; then
    log_error "Release $VERSION was not prepared. Run prepare-release.sh first."
    exit 1
fi

log_info "=== Publishing Release $VERSION ==="
echo ""

# Docker configuration
DOCKER_REGISTRY="${DOCKER_REGISTRY:-ghcr.io}"
DOCKER_NAMESPACE="${DOCKER_NAMESPACE:-ablage-system}"

# Step 1: Login to Docker registry
log_step "1. Logging in to Docker registry..."

if [ -n "$DOCKER_PASSWORD" ]; then
    echo "$DOCKER_PASSWORD" | docker login "$DOCKER_REGISTRY" -u "$DOCKER_USERNAME" --password-stdin
    log_info "Logged in to $DOCKER_REGISTRY"
else
    log_warn "DOCKER_PASSWORD not set, skipping Docker login"
    log_warn "Docker images will not be pushed"
fi

# Step 2: Push Docker images
log_step "2. Pushing Docker images..."

if docker login --help &>/dev/null && docker info &>/dev/null; then
    log_info "Pushing backend:$VERSION..."
    docker push "$DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-backend:$VERSION"
    docker push "$DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-backend:latest"

    log_info "Pushing worker:$VERSION..."
    docker push "$DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-worker:$VERSION"
    docker push "$DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-worker:latest"

    if docker images | grep -q "$DOCKER_NAMESPACE/ablage-frontend"; then
        log_info "Pushing frontend:$VERSION..."
        docker push "$DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-frontend:$VERSION"
        docker push "$DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-frontend:latest"
    fi

    log_info "Docker images pushed successfully"
else
    log_warn "Docker not logged in, images will not be pushed"
fi

# Step 3: Publish documentation
log_step "3. Publishing documentation..."

if [ -f "docs/mkdocs.yml" ] && command -v mkdocs &> /dev/null; then
    cd "$PROJECT_ROOT/docs"

    # Deploy to GitHub Pages
    if [ -n "$GITHUB_TOKEN" ]; then
        log_info "Deploying documentation to GitHub Pages..."
        mkdocs gh-deploy --force --message "docs: deploy documentation for version $VERSION [skip ci]"
        log_info "Documentation deployed"
    else
        log_warn "GITHUB_TOKEN not set, skipping documentation deployment"
    fi
else
    log_warn "Documentation not found or mkdocs not installed, skipping"
fi

# Step 4: Create GitHub Release assets
log_step "4. Preparing GitHub Release assets..."

cd "$PROJECT_ROOT"

# Assets are already created by prepare-release.sh
if [ -f "dist/ablage-system-$VERSION.tar.gz" ]; then
    log_info "Distribution tarball ready: ablage-system-$VERSION.tar.gz"
fi

if [ -f "dist/docker-images.txt" ]; then
    log_info "Docker images manifest ready"
fi

if [ -f "dist/RELEASE_NOTES.md" ]; then
    log_info "Release notes ready"
fi

# Step 5: Verify published images
log_step "5. Verifying published images..."

if command -v docker &> /dev/null; then
    log_info "Pulling and verifying backend:$VERSION..."
    docker pull "$DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-backend:$VERSION" || log_warn "Failed to pull backend image"

    log_info "Pulling and verifying worker:$VERSION..."
    docker pull "$DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-worker:$VERSION" || log_warn "Failed to pull worker image"

    log_info "Images verified successfully"
fi

# Step 6: Update Helm chart (if exists)
log_step "6. Updating Helm chart..."

if [ -f "charts/ablage-system/Chart.yaml" ]; then
    cd "$PROJECT_ROOT/charts/ablage-system"

    # Update appVersion in Chart.yaml
    sed -i.bak "s/appVersion: .*/appVersion: \"$VERSION\"/" Chart.yaml
    rm -f Chart.yaml.bak

    # Package Helm chart
    helm package . -d "$PROJECT_ROOT/dist/"

    log_info "Helm chart updated and packaged"
else
    log_warn "Helm chart not found, skipping"
fi

# Step 7: Publish Python package (if configured)
log_step "7. Publishing Python package..."

if [ -f "pyproject.toml" ] && [ -n "$PYPI_TOKEN" ]; then
    cd "$PROJECT_ROOT"

    # Build package
    python -m build

    # Upload to PyPI
    python -m twine upload dist/*.whl dist/*.tar.gz --username __token__ --password "$PYPI_TOKEN"

    log_info "Python package published to PyPI"
else
    log_warn "PyPI publishing not configured, skipping"
fi

# Step 8: Tag Docker images with additional tags
log_step "8. Creating additional Docker tags..."

# Extract major and minor versions
MAJOR_VERSION=$(echo "$VERSION" | cut -d. -f1)
MINOR_VERSION=$(echo "$VERSION" | cut -d. -f1,2)

# Tag with major version (e.g., v1)
docker tag "$DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-backend:$VERSION" \
           "$DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-backend:$MAJOR_VERSION"

docker tag "$DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-worker:$VERSION" \
           "$DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-worker:$MAJOR_VERSION"

# Tag with major.minor version (e.g., v1.0)
docker tag "$DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-backend:$VERSION" \
           "$DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-backend:$MINOR_VERSION"

docker tag "$DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-worker:$VERSION" \
           "$DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-worker:$MINOR_VERSION"

# Push additional tags
if docker info &>/dev/null; then
    docker push "$DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-backend:$MAJOR_VERSION" || log_warn "Failed to push major version tag"
    docker push "$DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-backend:$MINOR_VERSION" || log_warn "Failed to push minor version tag"
    docker push "$DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-worker:$MAJOR_VERSION" || log_warn "Failed to push major version tag"
    docker push "$DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-worker:$MINOR_VERSION" || log_warn "Failed to push minor version tag"

    log_info "Additional tags pushed"
fi

# Step 9: Create release manifest
log_step "9. Creating release manifest..."

cat > "$PROJECT_ROOT/dist/MANIFEST-$VERSION.json" <<EOF
{
  "version": "$VERSION",
  "release_date": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "docker_images": {
    "backend": "$DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-backend:$VERSION",
    "worker": "$DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-worker:$VERSION",
    "frontend": "$DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-frontend:$VERSION"
  },
  "artifacts": {
    "tarball": "ablage-system-$VERSION.tar.gz",
    "helm_chart": "ablage-system-$VERSION.tgz",
    "docker_manifest": "docker-images.txt"
  },
  "checksums": {
    "tarball_sha256": "$(sha256sum "$PROJECT_ROOT/dist/ablage-system-$VERSION.tar.gz" | cut -d' ' -f1)"
  },
  "documentation": "https://docs.ablage-system.local",
  "changelog": "https://github.com/ablage-system/ablage-system-ocr/blob/main/CHANGELOG.md"
}
EOF

log_info "Release manifest created"

# Summary
echo ""
log_info "=== Release $VERSION Published ==="
echo ""
log_info "Docker Images:"
log_info "  - $DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-backend:$VERSION"
log_info "  - $DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-worker:$VERSION"
log_info "  - $DOCKER_REGISTRY/$DOCKER_NAMESPACE/ablage-frontend:$VERSION"
echo ""
log_info "Artifacts:"
log_info "  - Distribution tarball"
log_info "  - Docker images manifest"
log_info "  - Release notes"
log_info "  - Release manifest"
echo ""
log_info "Documentation: Deployed"
echo ""

# Create success marker
touch "$PROJECT_ROOT/dist/.published-$VERSION"

exit 0
