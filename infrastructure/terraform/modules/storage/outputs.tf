# Storage Module Outputs

output "minio_volume_id" {
  description = "MinIO volume ID"
  value       = local.storage_config.minio_volume.name
}

output "postgres_volume_id" {
  description = "PostgreSQL volume ID"
  value       = local.storage_config.postgres_volume.name
}

output "backup_volume_id" {
  description = "Backup volume ID"
  value       = local.storage_config.backup_volume.name
}

output "prometheus_volume_id" {
  description = "Prometheus volume ID"
  value       = local.storage_config.prometheus_volume.name
}

output "storage_summary" {
  description = "Storage configuration summary"
  value = {
    total_gb           = var.minio_storage_size_gb + var.postgres_storage_size_gb + var.backup_storage_size_gb + var.prometheus_storage_size_gb
    minio_gb           = var.minio_storage_size_gb
    postgres_gb        = var.postgres_storage_size_gb
    backup_gb          = var.backup_storage_size_gb
    prometheus_gb      = var.prometheus_storage_size_gb
    retention_days     = var.backup_retention_days
    config_file        = local_file.storage_config.filename
    backup_policy_file = local_file.backup_policy.filename
  }
}
