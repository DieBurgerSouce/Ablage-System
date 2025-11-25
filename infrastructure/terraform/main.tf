# Terraform Configuration - Ablage-System OCR
# Main infrastructure definition

terraform {
  required_version = ">= 1.6.0"

  required_providers {
    proxmox = {
      source  = "telmate/proxmox"
      version = "~> 2.9"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.4"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }

  # Backend configuration for state storage
  backend "local" {
    path = "terraform.tfstate"
  }

  # For production, use remote backend:
  # backend "s3" {
  #   bucket         = "ablage-system-terraform-state"
  #   key            = "production/terraform.tfstate"
  #   region         = "eu-central-1"
  #   encrypt        = true
  #   dynamodb_table = "terraform-state-lock"
  # }
}

# Provider configuration
provider "proxmox" {
  pm_api_url      = var.proxmox_api_url
  pm_user         = var.proxmox_user
  pm_password     = var.proxmox_password
  pm_tls_insecure = var.proxmox_tls_insecure
  pm_parallel     = 2
  pm_timeout      = 600
}

# Local variables
locals {
  environment = var.environment
  project     = "ablage-system"

  common_tags = {
    Project     = local.project
    Environment = local.environment
    ManagedBy   = "Terraform"
    CreatedAt   = timestamp()
  }

  # Naming convention: {project}-{environment}-{resource}
  name_prefix = "${local.project}-${local.environment}"
}

# ============================================
# Networking Module
# ============================================

module "networking" {
  source = "./modules/networking"

  environment = var.environment
  name_prefix = local.name_prefix

  # Network configuration
  network_cidr        = var.network_cidr
  public_subnet_cidr  = var.public_subnet_cidr
  private_subnet_cidr = var.private_subnet_cidr

  # Firewall rules
  allowed_ssh_cidrs = var.allowed_ssh_cidrs
  allowed_http_cidrs = ["0.0.0.0/0"]  # Public access
  allowed_https_cidrs = ["0.0.0.0/0"] # Public access

  tags = local.common_tags
}

# ============================================
# Compute Module - Application Servers
# ============================================

module "compute" {
  source = "./modules/compute"

  environment = var.environment
  name_prefix = local.name_prefix

  # VM configuration
  backend_vm_count = var.backend_vm_count
  worker_vm_count  = var.worker_vm_count

  # Backend VM specs
  backend_vm_cores  = var.backend_vm_cores
  backend_vm_memory = var.backend_vm_memory
  backend_vm_disk   = var.backend_vm_disk

  # Worker VM specs (with GPU)
  worker_vm_cores  = var.worker_vm_cores
  worker_vm_memory = var.worker_vm_memory
  worker_vm_disk   = var.worker_vm_disk
  worker_gpu_type  = var.worker_gpu_type
  worker_gpu_count = var.worker_gpu_count

  # SSH configuration
  ssh_public_key = var.ssh_public_key

  # Networking
  network_id = module.networking.network_id
  subnet_id  = module.networking.private_subnet_id

  tags = local.common_tags

  depends_on = [module.networking]
}

# ============================================
# Storage Module
# ============================================

module "storage" {
  source = "./modules/storage"

  environment = var.environment
  name_prefix = local.name_prefix

  # Storage configuration
  minio_storage_size_gb      = var.minio_storage_size_gb
  postgres_storage_size_gb   = var.postgres_storage_size_gb
  backup_storage_size_gb     = var.backup_storage_size_gb
  prometheus_storage_size_gb = var.prometheus_storage_size_gb

  # Backup configuration
  backup_retention_days = var.backup_retention_days

  tags = local.common_tags
}

# ============================================
# Database Module
# ============================================

module "database" {
  source = "./modules/database"

  environment = var.environment
  name_prefix = local.name_prefix

  # PostgreSQL configuration
  postgres_version      = var.postgres_version
  postgres_vm_cores     = var.postgres_vm_cores
  postgres_vm_memory    = var.postgres_vm_memory
  postgres_disk_size_gb = var.postgres_storage_size_gb

  # Database settings
  postgres_max_connections = var.postgres_max_connections
  postgres_shared_buffers  = var.postgres_shared_buffers

  # Backup configuration
  postgres_backup_enabled   = var.postgres_backup_enabled
  postgres_backup_schedule  = var.postgres_backup_schedule
  postgres_backup_retention = var.backup_retention_days

  # Networking
  network_id     = module.networking.network_id
  subnet_id      = module.networking.private_subnet_id
  allowed_cidrs  = [module.networking.private_subnet_cidr]

  # Storage
  storage_volume_id = module.storage.postgres_volume_id

  tags = local.common_tags

  depends_on = [module.networking, module.storage]
}

# ============================================
# Load Balancer Module
# ============================================

module "load_balancer" {
  source = "./modules/load_balancer"

  environment = var.environment
  name_prefix = local.name_prefix

  # Load balancer configuration
  lb_vm_cores  = var.lb_vm_cores
  lb_vm_memory = var.lb_vm_memory

  # Backend targets
  backend_targets = module.compute.backend_vm_ips

  # SSL/TLS configuration
  enable_ssl     = var.enable_ssl
  ssl_cert_path  = var.ssl_cert_path
  ssl_key_path   = var.ssl_key_path
  domain_name    = var.domain_name

  # Health check configuration
  health_check_path     = "/health"
  health_check_interval = 30
  health_check_timeout  = 10

  # Networking
  network_id       = module.networking.network_id
  public_subnet_id = module.networking.public_subnet_id

  tags = local.common_tags

  depends_on = [module.networking, module.compute]
}

# ============================================
# Monitoring Module
# ============================================

module "monitoring" {
  source = "./modules/monitoring"

  environment = var.environment
  name_prefix = local.name_prefix

  # Monitoring VM configuration
  monitoring_vm_cores  = var.monitoring_vm_cores
  monitoring_vm_memory = var.monitoring_vm_memory
  monitoring_vm_disk   = var.monitoring_vm_disk

  # Prometheus configuration
  prometheus_retention_days = var.prometheus_retention_days
  prometheus_storage_size   = var.prometheus_storage_size_gb

  # Grafana configuration
  grafana_admin_password = var.grafana_admin_password

  # Alert configuration
  alertmanager_enabled = var.alertmanager_enabled
  alert_webhooks       = var.alert_webhooks

  # Targets to monitor
  backend_targets  = module.compute.backend_vm_ips
  worker_targets   = module.compute.worker_vm_ips
  database_targets = [module.database.postgres_vm_ip]
  lb_targets       = [module.load_balancer.lb_vm_ip]

  # Networking
  network_id = module.networking.network_id
  subnet_id  = module.networking.private_subnet_id

  # Storage
  prometheus_volume_id = module.storage.prometheus_volume_id

  tags = local.common_tags

  depends_on = [
    module.networking,
    module.compute,
    module.database,
    module.load_balancer,
    module.storage
  ]
}

# ============================================
# Outputs
# ============================================

output "load_balancer_ip" {
  description = "Public IP of load balancer"
  value       = module.load_balancer.public_ip
}

output "load_balancer_url" {
  description = "URL to access application"
  value       = module.load_balancer.application_url
}

output "grafana_url" {
  description = "URL to access Grafana"
  value       = module.monitoring.grafana_url
}

output "prometheus_url" {
  description = "URL to access Prometheus"
  value       = module.monitoring.prometheus_url
}

output "backend_vm_ips" {
  description = "IP addresses of backend VMs"
  value       = module.compute.backend_vm_ips
}

output "worker_vm_ips" {
  description = "IP addresses of worker VMs"
  value       = module.compute.worker_vm_ips
}

output "database_endpoint" {
  description = "PostgreSQL connection endpoint"
  value       = module.database.postgres_endpoint
  sensitive   = true
}

output "ssh_connection_commands" {
  description = "SSH commands to connect to VMs"
  value       = module.compute.ssh_commands
}
