# =============================================================================
# Terraform Backend Configuration for Ablage-System
# Uses MinIO (S3-compatible) for state storage
# =============================================================================
#
# This file defines the S3-compatible backend configuration for storing
# Terraform state in MinIO. State locking is handled externally via
# PostgreSQL using the terraform-lock-wrapper.sh script.
#
# Usage:
#   terraform init -backend-config=../environments/<env>/backend.hcl
#
# =============================================================================

terraform {
  required_version = ">= 1.6.0"

  # S3 backend configuration for MinIO
  # Environment-specific values are provided via backend.hcl files
  backend "s3" {
    # These values are placeholders - actual values come from backend.hcl
    # bucket = "terraform-state"
    # key    = "env/terraform.tfstate"

    # MinIO-specific settings (always required)
    region                      = "us-east-1"  # Required but ignored by MinIO
    force_path_style            = true         # Required for MinIO
    skip_credentials_validation = true         # MinIO doesn't support AWS credential validation
    skip_metadata_api_check     = true         # MinIO doesn't support IMDS
    skip_region_validation      = true         # Region is not used by MinIO
    skip_requesting_account_id  = true         # Not applicable for MinIO

    # Encryption at rest (MinIO server-side encryption)
    encrypt = true
  }

  required_providers {
    # Proxmox provider for VM provisioning
    proxmox = {
      source  = "telmate/proxmox"
      version = "~> 2.9"
    }

    # Local provider for local file operations
    local = {
      source  = "hashicorp/local"
      version = "~> 2.4"
    }

    # Null provider for provisioners
    null = {
      source  = "hashicorp/null"
      version = "~> 3.2"
    }

    # TLS provider for certificate generation
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }

    # Random provider for generating random values
    random = {
      source  = "hashicorp/random"
      version = "~> 3.5"
    }
  }
}

# =============================================================================
# State Locking Note
# =============================================================================
#
# Since MinIO doesn't natively support DynamoDB-style state locking, we use
# PostgreSQL for distributed lock management. The locking is handled by the
# terraform-lock-wrapper.sh script.
#
# Always use the wrapper script for operations that modify state:
#   ./backend/terraform-lock-wrapper.sh plan
#   ./backend/terraform-lock-wrapper.sh apply
#   ./backend/terraform-lock-wrapper.sh destroy
#
# For read-only operations, you can use terraform directly:
#   terraform show
#   terraform output
#   terraform state list
#
# =============================================================================

# =============================================================================
# Backend Migration Instructions
# =============================================================================
#
# To migrate from local state to MinIO backend:
#
# 1. Ensure MinIO bucket exists:
#    ./backend/minio-bucket-setup.sh
#
# 2. Ensure PostgreSQL lock table exists:
#    psql -f backend/state-lock-table.sql
#
# 3. Initialize with new backend:
#    terraform init -backend-config=environments/production/backend.hcl -migrate-state
#
# 4. Verify state migration:
#    terraform state list
#
# =============================================================================
