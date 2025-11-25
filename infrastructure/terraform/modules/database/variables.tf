# Database Module Variables

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "name_prefix" {
  description = "Name prefix for resources"
  type        = string
}

variable "postgres_version" {
  description = "PostgreSQL version"
  type        = string
}

variable "postgres_vm_cores" {
  description = "CPU cores for PostgreSQL VM"
  type        = number
}

variable "postgres_vm_memory" {
  description = "Memory in MB for PostgreSQL VM"
  type        = number
}

variable "postgres_disk_size_gb" {
  description = "Disk size in GB for PostgreSQL"
  type        = number
}

variable "postgres_max_connections" {
  description = "Maximum PostgreSQL connections"
  type        = number
}

variable "postgres_shared_buffers" {
  description = "PostgreSQL shared_buffers size"
  type        = string
}

variable "postgres_backup_enabled" {
  description = "Enable automated backups"
  type        = bool
}

variable "postgres_backup_schedule" {
  description = "Cron schedule for backups"
  type        = string
}

variable "postgres_backup_retention" {
  description = "Backup retention period in days"
  type        = number
}

variable "network_id" {
  description = "Network ID"
  type        = string
}

variable "subnet_id" {
  description = "Subnet ID"
  type        = string
}

variable "allowed_cidrs" {
  description = "Allowed CIDR blocks"
  type        = list(string)
}

variable "storage_volume_id" {
  description = "Storage volume ID"
  type        = string
}

variable "tags" {
  description = "Tags for resources"
  type        = map(string)
  default     = {}
}
