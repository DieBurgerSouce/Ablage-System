# Storage Module - Ablage-System OCR
# Persistent volumes for data storage

# Note: In Proxmox, storage is typically configured on the host level
# This module creates placeholder local files for tracking storage configuration

locals {
  storage_config = {
    minio_volume = {
      name    = "${var.name_prefix}-minio-storage"
      size_gb = var.minio_storage_size_gb
      mount   = "/mnt/minio"
    }
    postgres_volume = {
      name    = "${var.name_prefix}-postgres-storage"
      size_gb = var.postgres_storage_size_gb
      mount   = "/var/lib/postgresql"
    }
    backup_volume = {
      name    = "${var.name_prefix}-backup-storage"
      size_gb = var.backup_storage_size_gb
      mount   = "/mnt/backups"
    }
    prometheus_volume = {
      name    = "${var.name_prefix}-prometheus-storage"
      size_gb = var.prometheus_storage_size_gb
      mount   = "/var/lib/prometheus"
    }
  }
}

# Storage configuration file
resource "local_file" "storage_config" {
  filename = "${path.module}/storage-config.json"

  content = jsonencode(local.storage_config)
}

# Backup retention policy file
resource "local_file" "backup_policy" {
  filename = "${path.module}/backup-policy.txt"

  content = <<-EOT
    # Backup Policy - Ablage-System ${var.environment}

    Retention Period: ${var.backup_retention_days} days

    Storage Volumes:
    - MinIO: ${var.minio_storage_size_gb} GB
    - PostgreSQL: ${var.postgres_storage_size_gb} GB
    - Backups: ${var.backup_storage_size_gb} GB
    - Prometheus: ${var.prometheus_storage_size_gb} GB

    Total: ${var.minio_storage_size_gb + var.postgres_storage_size_gb + var.backup_storage_size_gb + var.prometheus_storage_size_gb} GB

    Backup Schedule:
    - Database: Daily at 02:00 UTC
    - MinIO: Weekly on Sunday at 03:00 UTC
    - Configuration: Daily at 04:00 UTC

    Cleanup:
    - Backups older than ${var.backup_retention_days} days are automatically deleted
    - Manual backups are never deleted automatically
  EOT
}
