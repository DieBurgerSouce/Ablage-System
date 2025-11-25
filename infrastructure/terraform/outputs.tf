# Outputs - Ablage-System OCR Terraform Configuration

# ============================================
# Application Access
# ============================================

output "application_url" {
  description = "Public URL to access the application"
  value       = "https://${var.domain_name}"
}

output "api_url" {
  description = "API endpoint URL"
  value       = "https://${var.domain_name}/api/v1"
}

output "api_docs_url" {
  description = "API documentation URL"
  value       = "https://${var.domain_name}/docs"
}

# ============================================
# Load Balancer
# ============================================

output "load_balancer_public_ip" {
  description = "Public IP address of the load balancer"
  value       = module.load_balancer.public_ip
}

output "load_balancer_private_ip" {
  description = "Private IP address of the load balancer"
  value       = module.load_balancer.private_ip
}

# ============================================
# Monitoring & Observability
# ============================================

output "grafana_url" {
  description = "Grafana dashboard URL"
  value       = "https://${var.domain_name}:3000"
}

output "grafana_admin_username" {
  description = "Grafana admin username"
  value       = "admin"
}

output "prometheus_url" {
  description = "Prometheus UI URL"
  value       = "https://${var.domain_name}:9090"
}

output "alertmanager_url" {
  description = "Alertmanager UI URL"
  value       = var.alertmanager_enabled ? "https://${var.domain_name}:9093" : null
}

# ============================================
# Backend VMs
# ============================================

output "backend_vm_count" {
  description = "Number of backend VMs deployed"
  value       = var.backend_vm_count
}

output "backend_vm_ips" {
  description = "IP addresses of backend VMs"
  value       = module.compute.backend_vm_ips
}

output "backend_ssh_commands" {
  description = "SSH commands to connect to backend VMs"
  value       = [for ip in module.compute.backend_vm_ips : "ssh -i ~/.ssh/id_rsa root@${ip}"]
}

# ============================================
# Worker VMs (GPU)
# ============================================

output "worker_vm_count" {
  description = "Number of worker VMs deployed"
  value       = var.worker_vm_count
}

output "worker_vm_ips" {
  description = "IP addresses of worker VMs"
  value       = module.compute.worker_vm_ips
}

output "worker_ssh_commands" {
  description = "SSH commands to connect to worker VMs"
  value       = [for ip in module.compute.worker_vm_ips : "ssh -i ~/.ssh/id_rsa root@${ip}"]
}

output "worker_gpu_info" {
  description = "GPU configuration for worker VMs"
  value = {
    gpu_type  = var.worker_gpu_type
    gpu_count = var.worker_gpu_count
    vm_count  = var.worker_vm_count
    total_gpus = var.worker_vm_count * var.worker_gpu_count
  }
}

# ============================================
# Database
# ============================================

output "database_endpoint" {
  description = "PostgreSQL connection endpoint"
  value       = module.database.postgres_endpoint
  sensitive   = true
}

output "database_port" {
  description = "PostgreSQL port"
  value       = 5432
}

output "database_name" {
  description = "PostgreSQL database name"
  value       = "ablage_system"
}

output "database_connection_string" {
  description = "PostgreSQL connection string (without password)"
  value       = "postgresql://ablage_user@${module.database.postgres_endpoint}:5432/ablage_system"
  sensitive   = true
}

# ============================================
# Storage
# ============================================

output "minio_endpoint" {
  description = "MinIO S3 endpoint"
  value       = "http://${module.compute.backend_vm_ips[0]}:9000"
}

output "minio_console_url" {
  description = "MinIO console URL"
  value       = "http://${module.compute.backend_vm_ips[0]}:9001"
}

output "storage_summary" {
  description = "Storage configuration summary"
  value = {
    minio_size_gb      = var.minio_storage_size_gb
    postgres_size_gb   = var.postgres_storage_size_gb
    backup_size_gb     = var.backup_storage_size_gb
    prometheus_size_gb = var.prometheus_storage_size_gb
    total_size_gb      = var.minio_storage_size_gb + var.postgres_storage_size_gb + var.backup_storage_size_gb + var.prometheus_storage_size_gb
  }
}

# ============================================
# Network Information
# ============================================

output "network_info" {
  description = "Network configuration summary"
  value = {
    network_cidr        = var.network_cidr
    public_subnet_cidr  = var.public_subnet_cidr
    private_subnet_cidr = var.private_subnet_cidr
  }
}

# ============================================
# Resource Summary
# ============================================

output "resource_summary" {
  description = "Summary of deployed resources"
  value = {
    environment = var.environment
    backend_vms = var.backend_vm_count
    worker_vms  = var.worker_vm_count
    total_vms   = var.backend_vm_count + var.worker_vm_count + 3  # +3 for LB, DB, Monitoring

    total_cpu_cores = (
      var.backend_vm_count * var.backend_vm_cores +
      var.worker_vm_count * var.worker_vm_cores +
      var.postgres_vm_cores +
      var.lb_vm_cores +
      var.monitoring_vm_cores
    )

    total_memory_gb = (
      var.backend_vm_count * var.backend_vm_memory +
      var.worker_vm_count * var.worker_vm_memory +
      var.postgres_vm_memory +
      var.lb_vm_memory +
      var.monitoring_vm_memory
    ) / 1024

    total_storage_gb = (
      var.backend_vm_count * var.backend_vm_disk +
      var.worker_vm_count * var.worker_vm_disk +
      var.postgres_storage_size_gb +
      var.minio_storage_size_gb +
      var.backup_storage_size_gb +
      var.prometheus_storage_size_gb +
      var.monitoring_vm_disk
    )

    total_gpus = var.worker_vm_count * var.worker_gpu_count
  }
}

# ============================================
# Cost Estimation
# ============================================

output "estimated_monthly_cost_usd" {
  description = "Estimated monthly infrastructure cost (rough estimate)"
  value = {
    compute_cost    = (var.backend_vm_count + var.worker_vm_count + 3) * 50  # $50/VM
    storage_cost    = (var.minio_storage_size_gb + var.postgres_storage_size_gb + var.backup_storage_size_gb + var.prometheus_storage_size_gb) * 0.10  # $0.10/GB
    gpu_cost        = var.worker_vm_count * var.worker_gpu_count * 300  # $300/GPU
    total_estimated = (var.backend_vm_count + var.worker_vm_count + 3) * 50 + (var.minio_storage_size_gb + var.postgres_storage_size_gb + var.backup_storage_size_gb + var.prometheus_storage_size_gb) * 0.10 + var.worker_vm_count * var.worker_gpu_count * 300
    note            = "This is a rough estimate. Actual costs may vary based on provider and usage."
  }
}

# ============================================
# Deployment Information
# ============================================

output "deployment_timestamp" {
  description = "Timestamp of deployment"
  value       = timestamp()
}

output "terraform_version" {
  description = "Terraform version used"
  value       = "~> 1.6.0"
}

# ============================================
# Next Steps
# ============================================

output "next_steps" {
  description = "Next steps after deployment"
  value = <<-EOT
    Deployment complete! 🎉

    Next steps:
    1. Configure DNS:
       - Point ${var.domain_name} to ${module.load_balancer.public_ip}

    2. Access services:
       - Application: https://${var.domain_name}
       - API Docs: https://${var.domain_name}/docs
       - Grafana: https://${var.domain_name}:3000 (admin / ${var.grafana_admin_password})
       - Prometheus: https://${var.domain_name}:9090

    3. Configure application:
       - SSH to backend: ssh root@${module.compute.backend_vm_ips[0]}
       - Update .env file: /opt/ablage-system/.env
       - Start services: systemctl start ablage-system.target

    4. Verify GPU access (on worker VMs):
       - SSH to worker: ssh root@${module.compute.worker_vm_ips[0]}
       - Check GPU: nvidia-smi

    5. Configure monitoring:
       - Import Grafana dashboards: /opt/ablage-system/infrastructure/monitoring/grafana/dashboards/
       - Set up alert channels in Grafana UI

    6. Security hardening:
       - Update firewall rules: restrict SSH access
       - Rotate default passwords
       - Enable fail2ban
       - Configure automatic security updates

    7. Backups:
       - Verify backup schedule: systemctl status ablage-backup.timer
       - Test restore procedure: /opt/ablage-system/scripts/restore.sh

    For detailed documentation, see: /opt/ablage-system/DEPLOYMENT.md
  EOT
}
