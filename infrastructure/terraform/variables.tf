# Variables - Ablage-System OCR Terraform Configuration

# ============================================
# General Configuration
# ============================================

variable "environment" {
  description = "Environment name (dev, staging, production)"
  type        = string
  default     = "production"

  validation {
    condition     = contains(["dev", "staging", "production"], var.environment)
    error_message = "Environment must be one of: dev, staging, production."
  }
}

# ============================================
# Proxmox Provider Configuration
# ============================================

variable "proxmox_api_url" {
  description = "Proxmox API URL (e.g., https://proxmox.example.com:8006/api2/json)"
  type        = string
}

variable "proxmox_user" {
  description = "Proxmox user (e.g., root@pam)"
  type        = string
}

variable "proxmox_password" {
  description = "Proxmox password"
  type        = string
  sensitive   = true
}

variable "proxmox_tls_insecure" {
  description = "Skip TLS verification for Proxmox API"
  type        = bool
  default     = false
}

# ============================================
# Networking Configuration
# ============================================

variable "network_cidr" {
  description = "CIDR block for main network"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidr" {
  description = "CIDR block for public subnet"
  type        = string
  default     = "10.0.1.0/24"
}

variable "private_subnet_cidr" {
  description = "CIDR block for private subnet"
  type        = string
  default     = "10.0.2.0/24"
}

variable "allowed_ssh_cidrs" {
  description = "CIDR blocks allowed to SSH - SECURITY: Restrict to your IP range!"
  type        = list(string)
  # SECURITY FIX: No default - must be explicitly set to prevent open SSH
  # Example: ["10.0.0.0/8"] for internal network or ["YOUR.IP.ADDRESS/32"] for single IP
}

# ============================================
# SSH Configuration
# ============================================

variable "ssh_public_key" {
  description = "SSH public key for VM access"
  type        = string
}

# ============================================
# Backend VM Configuration
# ============================================

variable "backend_vm_count" {
  description = "Number of backend VMs"
  type        = number
  default     = 2

  validation {
    condition     = var.backend_vm_count >= 1 && var.backend_vm_count <= 10
    error_message = "Backend VM count must be between 1 and 10."
  }
}

variable "backend_vm_cores" {
  description = "Number of CPU cores for backend VMs"
  type        = number
  default     = 4
}

variable "backend_vm_memory" {
  description = "Memory in MB for backend VMs"
  type        = number
  default     = 8192  # 8 GB
}

variable "backend_vm_disk" {
  description = "Disk size in GB for backend VMs"
  type        = number
  default     = 100
}

# ============================================
# Worker VM Configuration (GPU)
# ============================================

variable "worker_vm_count" {
  description = "Number of worker VMs"
  type        = number
  default     = 2

  validation {
    condition     = var.worker_vm_count >= 1 && var.worker_vm_count <= 5
    error_message = "Worker VM count must be between 1 and 5."
  }
}

variable "worker_vm_cores" {
  description = "Number of CPU cores for worker VMs"
  type        = number
  default     = 8
}

variable "worker_vm_memory" {
  description = "Memory in MB for worker VMs"
  type        = number
  default     = 32768  # 32 GB
}

variable "worker_vm_disk" {
  description = "Disk size in GB for worker VMs"
  type        = number
  default     = 200
}

variable "worker_gpu_type" {
  description = "GPU type for worker VMs (e.g., nvidia-rtx-4080)"
  type        = string
  default     = "nvidia-rtx-4080"
}

variable "worker_gpu_count" {
  description = "Number of GPUs per worker VM"
  type        = number
  default     = 1
}

# ============================================
# Database Configuration
# ============================================

variable "postgres_version" {
  description = "PostgreSQL version"
  type        = string
  default     = "16"
}

variable "postgres_vm_cores" {
  description = "Number of CPU cores for PostgreSQL VM"
  type        = number
  default     = 4
}

variable "postgres_vm_memory" {
  description = "Memory in MB for PostgreSQL VM"
  type        = number
  default     = 16384  # 16 GB
}

variable "postgres_max_connections" {
  description = "Maximum PostgreSQL connections"
  type        = number
  default     = 200
}

variable "postgres_shared_buffers" {
  description = "PostgreSQL shared_buffers size (e.g., '4GB')"
  type        = string
  default     = "4GB"
}

variable "postgres_backup_enabled" {
  description = "Enable automated PostgreSQL backups"
  type        = bool
  default     = true
}

variable "postgres_backup_schedule" {
  description = "Cron schedule for PostgreSQL backups"
  type        = string
  default     = "0 2 * * *"  # Daily at 2 AM
}

# ============================================
# Storage Configuration
# ============================================

variable "minio_storage_size_gb" {
  description = "Storage size in GB for MinIO"
  type        = number
  default     = 500
}

variable "postgres_storage_size_gb" {
  description = "Storage size in GB for PostgreSQL"
  type        = number
  default     = 200
}

variable "backup_storage_size_gb" {
  description = "Storage size in GB for backups"
  type        = number
  default     = 1000
}

variable "prometheus_storage_size_gb" {
  description = "Storage size in GB for Prometheus"
  type        = number
  default     = 100
}

variable "backup_retention_days" {
  description = "Number of days to retain backups"
  type        = number
  default     = 30
}

# ============================================
# Load Balancer Configuration
# ============================================

variable "lb_vm_cores" {
  description = "Number of CPU cores for load balancer VM"
  type        = number
  default     = 2
}

variable "lb_vm_memory" {
  description = "Memory in MB for load balancer VM"
  type        = number
  default     = 4096  # 4 GB
}

variable "enable_ssl" {
  description = "Enable SSL/TLS on load balancer"
  type        = bool
  default     = true
}

variable "ssl_cert_path" {
  description = "Path to SSL certificate file"
  type        = string
  default     = ""
}

variable "ssl_key_path" {
  description = "Path to SSL private key file"
  type        = string
  default     = ""
}

variable "domain_name" {
  description = "Domain name for the application"
  type        = string
  default     = "ablage-system.local"
}

# ============================================
# Monitoring Configuration
# ============================================

variable "monitoring_vm_cores" {
  description = "Number of CPU cores for monitoring VM"
  type        = number
  default     = 4
}

variable "monitoring_vm_memory" {
  description = "Memory in MB for monitoring VM"
  type        = number
  default     = 8192  # 8 GB
}

variable "monitoring_vm_disk" {
  description = "Disk size in GB for monitoring VM"
  type        = number
  default     = 100
}

variable "prometheus_retention_days" {
  description = "Number of days to retain Prometheus metrics"
  type        = number
  default     = 30
}

variable "grafana_admin_password" {
  description = "Grafana admin password"
  type        = string
  sensitive   = true
  default     = ""  # Generated if not provided
}

variable "alertmanager_enabled" {
  description = "Enable Alertmanager"
  type        = bool
  default     = true
}

variable "alert_webhooks" {
  description = "Webhook URLs for alerts"
  type        = map(string)
  default     = {}
  sensitive   = true
}

# ============================================
# Tags
# ============================================

variable "additional_tags" {
  description = "Additional tags to apply to all resources"
  type        = map(string)
  default     = {}
}
