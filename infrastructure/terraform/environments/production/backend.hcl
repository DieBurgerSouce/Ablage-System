# =============================================================================
# Terraform Backend Configuration - Production Environment
# Ablage-System OCR Infrastructure
# =============================================================================
#
# Usage:
#   terraform init -backend-config=environments/production/backend.hcl
#
# Environment Variables Required:
#   AWS_ACCESS_KEY_ID     - MinIO access key
#   AWS_SECRET_ACCESS_KEY - MinIO secret key
#
# IMPORTANT: Always use terraform-lock-wrapper.sh for production operations!
#   ./backend/terraform-lock-wrapper.sh plan
#   ./backend/terraform-lock-wrapper.sh apply
#
# =============================================================================

# MinIO bucket for Terraform state
bucket = "terraform-state"

# State file path within the bucket
key = "production/terraform.tfstate"

# MinIO endpoint (on-premises)
endpoint = "http://minio.ablage-system.local:9000"

# Required for MinIO compatibility
region                      = "us-east-1"
force_path_style            = true
skip_credentials_validation = true
skip_metadata_api_check     = true
skip_region_validation      = true
skip_requesting_account_id  = true

# Enable server-side encryption
encrypt = true
