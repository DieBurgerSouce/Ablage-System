# Storage Module Variables

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "name_prefix" {
  description = "Name prefix for resources"
  type        = string
}

variable "minio_storage_size_gb" {
  description = "MinIO storage size in GB"
  type        = number
}

variable "postgres_storage_size_gb" {
  description = "PostgreSQL storage size in GB"
  type        = number
}

variable "backup_storage_size_gb" {
  description = "Backup storage size in GB"
  type        = number
}

variable "prometheus_storage_size_gb" {
  description = "Prometheus storage size in GB"
  type        = number
}

variable "backup_retention_days" {
  description = "Backup retention period in days"
  type        = number
}

variable "tags" {
  description = "Tags for resources"
  type        = map(string)
  default     = {}
}
