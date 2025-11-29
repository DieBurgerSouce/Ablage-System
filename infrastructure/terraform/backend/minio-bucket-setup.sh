#!/bin/bash
# =============================================================================
# MinIO Bucket Setup for Terraform State Storage
# Ablage-System OCR Infrastructure
# =============================================================================
#
# This script creates and configures the MinIO bucket used for storing
# Terraform state files. It sets up versioning, lifecycle policies, and
# appropriate access controls.
#
# Prerequisites:
#   - MinIO client (mc) installed: https://min.io/docs/minio/linux/reference/minio-mc.html
#   - MinIO server running and accessible
#   - Environment variables set (see below)
#
# Usage:
#   export MINIO_ROOT_USER=admin
#   export MINIO_ROOT_PASSWORD=your-secure-password
#   ./minio-bucket-setup.sh
#
# =============================================================================

set -euo pipefail

# Configuration with defaults
MINIO_ENDPOINT="${MINIO_ENDPOINT:-localhost:9000}"
MINIO_USE_SSL="${MINIO_USE_SSL:-false}"
MINIO_ACCESS_KEY="${MINIO_ROOT_USER:-}"
MINIO_SECRET_KEY="${MINIO_ROOT_PASSWORD:-}"
BUCKET_NAME="${TF_STATE_BUCKET:-terraform-state}"
ALIAS_NAME="ablage-minio"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Prüfe Voraussetzungen..."

    # Check mc is installed
    if ! command -v mc &> /dev/null; then
        log_error "MinIO Client (mc) ist nicht installiert."
        log_info "Installation: curl https://dl.min.io/client/mc/release/linux-amd64/mc -o /usr/local/bin/mc && chmod +x /usr/local/bin/mc"
        exit 1
    fi

    # Check credentials
    if [[ -z "$MINIO_ACCESS_KEY" || -z "$MINIO_SECRET_KEY" ]]; then
        log_error "MINIO_ROOT_USER und MINIO_ROOT_PASSWORD müssen gesetzt sein."
        exit 1
    fi

    log_info "Voraussetzungen erfüllt."
}

# Configure MinIO client alias
configure_alias() {
    log_info "Konfiguriere MinIO-Alias: $ALIAS_NAME"

    local protocol="http"
    if [[ "$MINIO_USE_SSL" == "true" ]]; then
        protocol="https"
    fi

    mc alias set "$ALIAS_NAME" "${protocol}://${MINIO_ENDPOINT}" "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY" --api S3v4

    # Verify connection
    if ! mc admin info "$ALIAS_NAME" &> /dev/null; then
        log_error "Verbindung zu MinIO fehlgeschlagen. Überprüfe Endpoint und Zugangsdaten."
        exit 1
    fi

    log_info "MinIO-Verbindung erfolgreich."
}

# Create bucket if not exists
create_bucket() {
    log_info "Erstelle Bucket: $BUCKET_NAME"

    if mc ls "$ALIAS_NAME/$BUCKET_NAME" &> /dev/null; then
        log_warn "Bucket '$BUCKET_NAME' existiert bereits."
    else
        mc mb "$ALIAS_NAME/$BUCKET_NAME"
        log_info "Bucket '$BUCKET_NAME' erfolgreich erstellt."
    fi
}

# Enable versioning
enable_versioning() {
    log_info "Aktiviere Versionierung für Bucket: $BUCKET_NAME"

    mc version enable "$ALIAS_NAME/$BUCKET_NAME"
    log_info "Versionierung aktiviert."
}

# Set bucket policy (private by default)
set_bucket_policy() {
    log_info "Setze Bucket-Policy auf 'private'"

    # Create a strict policy for Terraform state
    cat > /tmp/terraform-state-policy.json << 'EOF'
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {"AWS": ["*"]},
            "Action": [
                "s3:GetObject",
                "s3:PutObject",
                "s3:DeleteObject",
                "s3:ListBucket"
            ],
            "Resource": [
                "arn:aws:s3:::terraform-state",
                "arn:aws:s3:::terraform-state/*"
            ],
            "Condition": {
                "IpAddress": {
                    "aws:SourceIp": ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]
                }
            }
        }
    ]
}
EOF

    # For internal use, set to private (requires authentication)
    mc anonymous set none "$ALIAS_NAME/$BUCKET_NAME"
    log_info "Bucket ist privat und erfordert Authentifizierung."
}

# Configure lifecycle policy for old versions
configure_lifecycle() {
    log_info "Konfiguriere Lifecycle-Policy für alte Versionen"

    cat > /tmp/terraform-lifecycle.json << EOF
{
    "Rules": [
        {
            "ID": "cleanup-old-versions",
            "Status": "Enabled",
            "Filter": {
                "Prefix": ""
            },
            "NoncurrentVersionExpiration": {
                "NoncurrentDays": 90
            }
        },
        {
            "ID": "cleanup-incomplete-uploads",
            "Status": "Enabled",
            "Filter": {
                "Prefix": ""
            },
            "AbortIncompleteMultipartUpload": {
                "DaysAfterInitiation": 7
            }
        }
    ]
}
EOF

    mc ilm import "$ALIAS_NAME/$BUCKET_NAME" < /tmp/terraform-lifecycle.json
    log_info "Lifecycle-Policy konfiguriert: Alte Versionen nach 90 Tagen löschen."
}

# Create directory structure for environments
create_directory_structure() {
    log_info "Erstelle Verzeichnisstruktur für Umgebungen"

    # Create placeholder files for each environment to establish directory structure
    for env in dev staging production; do
        echo "# Terraform state placeholder for $env environment" | mc pipe "$ALIAS_NAME/$BUCKET_NAME/$env/.keep"
        log_info "  - $env/ erstellt"
    done
}

# Verify setup
verify_setup() {
    log_info "Überprüfe Setup..."

    echo ""
    echo "=========================================="
    echo "MinIO Terraform State Bucket - Übersicht"
    echo "=========================================="
    echo ""

    # Bucket info
    echo "Bucket: $BUCKET_NAME"
    echo "Endpoint: $MINIO_ENDPOINT"
    echo ""

    # Versioning status
    echo "Versionierung:"
    mc version info "$ALIAS_NAME/$BUCKET_NAME"
    echo ""

    # List contents
    echo "Inhalt:"
    mc ls "$ALIAS_NAME/$BUCKET_NAME"
    echo ""

    # Lifecycle rules
    echo "Lifecycle-Regeln:"
    mc ilm ls "$ALIAS_NAME/$BUCKET_NAME"
    echo ""

    log_info "Setup abgeschlossen!"
}

# Print usage instructions
print_usage() {
    echo ""
    echo "=========================================="
    echo "Verwendung mit Terraform"
    echo "=========================================="
    echo ""
    echo "1. Backend-Konfiguration in backend.hcl:"
    echo ""
    echo "   bucket                      = \"$BUCKET_NAME\""
    echo "   key                         = \"production/terraform.tfstate\""
    echo "   region                      = \"us-east-1\""
    echo "   endpoint                    = \"http://$MINIO_ENDPOINT\""
    echo "   force_path_style           = true"
    echo "   skip_credentials_validation = true"
    echo "   skip_metadata_api_check    = true"
    echo "   skip_region_validation     = true"
    echo "   encrypt                    = true"
    echo ""
    echo "2. Initialisierung:"
    echo ""
    echo "   export AWS_ACCESS_KEY_ID=\"$MINIO_ACCESS_KEY\""
    echo "   export AWS_SECRET_ACCESS_KEY=\"\$MINIO_ROOT_PASSWORD\""
    echo "   terraform init -backend-config=backend.hcl"
    echo ""
    echo "=========================================="
}

# Cleanup function
cleanup() {
    rm -f /tmp/terraform-state-policy.json /tmp/terraform-lifecycle.json 2>/dev/null || true
}

# Main execution
main() {
    trap cleanup EXIT

    echo ""
    echo "=========================================="
    echo "MinIO Bucket Setup für Terraform State"
    echo "Ablage-System OCR Infrastructure"
    echo "=========================================="
    echo ""

    check_prerequisites
    configure_alias
    create_bucket
    enable_versioning
    set_bucket_policy
    configure_lifecycle
    create_directory_structure
    verify_setup
    print_usage
}

# Run main function
main "$@"
