# Monitoring Module Variables

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "name_prefix" {
  description = "Name prefix for resources"
  type        = string
}

variable "monitoring_vm_cores" {
  description = "CPU cores for monitoring VM"
  type        = number
}

variable "monitoring_vm_memory" {
  description = "Memory in MB for monitoring VM"
  type        = number
}

variable "monitoring_vm_disk" {
  description = "Disk size in GB for monitoring VM"
  type        = number
}

variable "prometheus_retention_days" {
  description = "Prometheus data retention in days"
  type        = number
}

variable "prometheus_storage_size" {
  description = "Prometheus storage size in GB"
  type        = number
}

variable "grafana_admin_password" {
  description = "Grafana admin password"
  type        = string
  sensitive   = true
}

variable "alertmanager_enabled" {
  description = "Enable Alertmanager"
  type        = bool
}

variable "alert_webhooks" {
  description = "Alert webhook URLs"
  type        = map(string)
  sensitive   = true
}

variable "backend_targets" {
  description = "Backend VM IPs to monitor"
  type        = list(string)
}

variable "worker_targets" {
  description = "Worker VM IPs to monitor"
  type        = list(string)
}

variable "database_targets" {
  description = "Database VM IPs to monitor"
  type        = list(string)
}

variable "lb_targets" {
  description = "Load balancer VM IPs to monitor"
  type        = list(string)
}

variable "network_id" {
  description = "Network ID"
  type        = string
}

variable "subnet_id" {
  description = "Subnet ID"
  type        = string
}

variable "prometheus_volume_id" {
  description = "Prometheus volume ID"
  type        = string
}

variable "tags" {
  description = "Tags for resources"
  type        = map(string)
  default     = {}
}
