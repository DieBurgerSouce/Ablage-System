# Terraform Infrastructure Guide
**Ablage-System - Infrastructure as Code mit Terraform**

Version: 1.0
Last Updated: 2025-01-23
Owner: DevOps Team
Status: PRODUCTION

---

## Executive Summary

Complete Terraform infrastructure provisioning guide for Ablage-System, covering on-premises infrastructure automation, state management, and production best practices.

**Key Features:**
- ✅ Infrastructure as Code: 100% reproducible infrastructure
- ✅ State Management: Remote state with locking
- ✅ Modular Design: Reusable modules for all components
- ✅ Multi-Environment: Dev, staging, production workspaces

---

## Table of Contents

1. [Terraform Architecture](#terraform-architecture)
2. [Project Structure](#project-structure)
3. [Core Modules](#core-modules)
4. [State Management](#state-management)
5. [Environment Management](#environment-management)
6. [Production Patterns](#production-patterns)
7. [Security Best Practices](#security-best-practices)

---

## Terraform Architecture

### Infrastructure Components

```
Ablage-System Infrastructure
├── Compute Resources
│   ├── GPU Server (RTX 4080)
│   ├── Application Servers
│   └── Database Server
│
├── Network Configuration
│   ├── Virtual Networks
│   ├── Firewall Rules
│   └── Load Balancers
│
├── Storage
│   ├── Block Storage (SSD)
│   ├── Object Storage (MinIO)
│   └── Backup Storage
│
└── Monitoring & Logging
    ├── Prometheus
    ├── Grafana
    └── Loki
```

### Technology Stack

- **Terraform:** v1.6+
- **Providers:**
  - libvirt (KVM/QEMU for on-premises VMs)
  - docker (container management)
  - null (provisioning hooks)
- **Backend:** Local or remote (Terraform Cloud/S3-compatible)

---

## Project Structure

```
infrastructure/terraform/
├── main.tf                    # Root module entry point
├── variables.tf               # Input variables
├── outputs.tf                 # Output values
├── versions.tf                # Provider versions
├── terraform.tfvars           # Default variable values (gitignored)
├── backend.tf                 # State backend configuration
│
├── environments/
│   ├── dev/
│   │   ├── main.tf
│   │   ├── terraform.tfvars
│   │   └── backend.tf
│   ├── staging/
│   │   ├── main.tf
│   │   ├── terraform.tfvars
│   │   └── backend.tf
│   └── production/
│       ├── main.tf
│       ├── terraform.tfvars
│       └── backend.tf
│
└── modules/
    ├── compute/
    │   ├── main.tf
    │   ├── variables.tf
    │   ├── outputs.tf
    │   └── README.md
    ├── network/
    │   ├── main.tf
    │   ├── variables.tf
    │   └── outputs.tf
    ├── storage/
    │   ├── main.tf
    │   ├── variables.tf
    │   └── outputs.tf
    └── monitoring/
        ├── main.tf
        ├── variables.tf
        └── outputs.tf
```

---

## Core Modules

### 1. Compute Module

```hcl
# modules/compute/main.tf
# Provisions GPU-enabled server for OCR processing

terraform {
  required_version = ">= 1.6.0"
  required_providers {
    libvirt = {
      source  = "dmacvicar/libvirt"
      version = "~> 0.7.0"
    }
  }
}

resource "libvirt_volume" "ablage_server" {
  name   = "ablage-${var.environment}-server.qcow2"
  pool   = var.storage_pool
  source = var.base_image_url
  format = "qcow2"
}

resource "libvirt_domain" "ablage_server" {
  name   = "ablage-${var.environment}-server"
  memory = var.memory_mb
  vcpu   = var.vcpu_count

  # GPU Passthrough for RTX 4080
  dynamic "hostdev" {
    for_each = var.enable_gpu ? [1] : []
    content {
      source {
        address {
          type     = "pci"
          domain   = "0x0000"
          bus      = var.gpu_pci_bus
          slot     = var.gpu_pci_slot
          function = var.gpu_pci_function
        }
      }
    }
  }

  disk {
    volume_id = libvirt_volume.ablage_server.id
  }

  network_interface {
    network_name   = var.network_name
    wait_for_lease = true
  }

  console {
    type        = "pty"
    target_type = "serial"
    target_port = "0"
  }

  graphics {
    type        = "vnc"
    listen_type = "address"
    autoport    = true
  }

  # Cloud-init for initial configuration
  cloudinit = libvirt_cloudinit_disk.init.id
}

resource "libvirt_cloudinit_disk" "init" {
  name      = "ablage-${var.environment}-init.iso"
  pool      = var.storage_pool
  user_data = data.template_file.user_data.rendered
}

data "template_file" "user_data" {
  template = file("${path.module}/cloud_init.yaml")

  vars = {
    hostname        = "ablage-${var.environment}"
    ssh_public_key  = var.ssh_public_key
    docker_version  = var.docker_version
    nvidia_driver   = var.nvidia_driver_version
  }
}
```

### Module Variables

```hcl
# modules/compute/variables.tf

variable "environment" {
  description = "Environment name (dev, staging, production)"
  type        = string
  validation {
    condition     = contains(["dev", "staging", "production"], var.environment)
    error_message = "Environment must be dev, staging, or production."
  }
}

variable "memory_mb" {
  description = "Memory in MB"
  type        = number
  default     = 16384  # 16 GB

  validation {
    condition     = var.memory_mb >= 8192
    error_message = "Minimum 8GB RAM required."
  }
}

variable "vcpu_count" {
  description = "Number of virtual CPUs"
  type        = number
  default     = 8
}

variable "enable_gpu" {
  description = "Enable GPU passthrough"
  type        = bool
  default     = false
}

variable "gpu_pci_bus" {
  description = "PCI bus address for GPU"
  type        = string
  default     = "0x01"
}

variable "gpu_pci_slot" {
  description = "PCI slot address for GPU"
  type        = string
  default     = "0x00"
}

variable "gpu_pci_function" {
  description = "PCI function for GPU"
  type        = string
  default     = "0x0"
}

variable "storage_pool" {
  description = "Libvirt storage pool name"
  type        = string
  default     = "default"
}

variable "base_image_url" {
  description = "Base Ubuntu image URL"
  type        = string
  default     = "https://cloud-images.ubuntu.com/releases/22.04/release/ubuntu-22.04-server-cloudimg-amd64.img"
}

variable "network_name" {
  description = "Libvirt network name"
  type        = string
  default     = "default"
}

variable "ssh_public_key" {
  description = "SSH public key for server access"
  type        = string
  sensitive   = true
}

variable "docker_version" {
  description = "Docker version to install"
  type        = string
  default     = "24.0.7"
}

variable "nvidia_driver_version" {
  description = "NVIDIA driver version"
  type        = string
  default     = "535.129.03"
}
```

### Module Outputs

```hcl
# modules/compute/outputs.tf

output "server_id" {
  description = "Server domain ID"
  value       = libvirt_domain.ablage_server.id
}

output "server_ip" {
  description = "Server IP address"
  value       = libvirt_domain.ablage_server.network_interface[0].addresses[0]
}

output "server_name" {
  description = "Server hostname"
  value       = libvirt_domain.ablage_server.name
}

output "gpu_enabled" {
  description = "Whether GPU is enabled"
  value       = var.enable_gpu
}
```

---

### 2. Network Module

```hcl
# modules/network/main.tf
# Creates virtual network with firewall rules

resource "libvirt_network" "ablage_network" {
  name      = "ablage-${var.environment}-network"
  mode      = "nat"
  domain    = "ablage.local"
  addresses = [var.network_cidr]

  dns {
    enabled = true
  }

  dhcp {
    enabled = true
  }
}

# Firewall rules (using null_resource with iptables)
resource "null_resource" "firewall_rules" {
  triggers = {
    rules_version = md5(file("${path.module}/firewall_rules.sh"))
  }

  provisioner "local-exec" {
    command = "${path.module}/firewall_rules.sh ${var.environment}"
  }
}
```

### Firewall Rules Script

```bash
#!/bin/bash
# modules/network/firewall_rules.sh

ENVIRONMENT=$1

# Allow SSH
iptables -A INPUT -p tcp --dport 22 -j ACCEPT

# Allow HTTP/HTTPS
iptables -A INPUT -p tcp --dport 80 -j ACCEPT
iptables -A INPUT -p tcp --dport 443 -j ACCEPT

# Allow Ablage API (8000)
iptables -A INPUT -p tcp --dport 8000 -j ACCEPT

# Allow PostgreSQL (internal only)
iptables -A INPUT -p tcp --dport 5432 -s 172.28.0.0/16 -j ACCEPT
iptables -A INPUT -p tcp --dport 5432 -j DROP

# Allow Redis (internal only)
iptables -A INPUT -p tcp --dport 6379 -s 172.28.0.0/16 -j ACCEPT
iptables -A INPUT -p tcp --dport 6379 -j DROP

# Allow MinIO (internal only)
iptables -A INPUT -p tcp --dport 9000 -s 172.28.0.0/16 -j ACCEPT
iptables -A INPUT -p tcp --dport 9000 -j DROP

# Drop all other traffic
iptables -A INPUT -j DROP

# Save rules
iptables-save > /etc/iptables/rules.v4

echo "Firewall rules applied for $ENVIRONMENT"
```

---

### 3. Storage Module

```hcl
# modules/storage/main.tf
# Provisions storage volumes for data persistence

resource "libvirt_pool" "ablage_storage" {
  name = "ablage-${var.environment}-storage"
  type = "dir"
  path = var.storage_path
}

resource "libvirt_volume" "postgres_data" {
  name   = "ablage-${var.environment}-postgres-data.qcow2"
  pool   = libvirt_pool.ablage_storage.name
  format = "qcow2"
  size   = var.postgres_volume_size_gb * 1024 * 1024 * 1024  # Convert GB to bytes
}

resource "libvirt_volume" "minio_data" {
  name   = "ablage-${var.environment}-minio-data.qcow2"
  pool   = libvirt_pool.ablage_storage.name
  format = "qcow2"
  size   = var.minio_volume_size_gb * 1024 * 1024 * 1024
}

resource "libvirt_volume" "redis_data" {
  name   = "ablage-${var.environment}-redis-data.qcow2"
  pool   = libvirt_pool.ablage_storage.name
  format = "qcow2"
  size   = var.redis_volume_size_gb * 1024 * 1024 * 1024
}

# Backup volumes
resource "libvirt_volume" "backup" {
  name   = "ablage-${var.environment}-backup.qcow2"
  pool   = libvirt_pool.ablage_storage.name
  format = "qcow2"
  size   = var.backup_volume_size_gb * 1024 * 1024 * 1024
}
```

---

### 4. Monitoring Module

```hcl
# modules/monitoring/main.tf
# Deploys Prometheus, Grafana, Loki for observability

resource "docker_container" "prometheus" {
  name  = "ablage-${var.environment}-prometheus"
  image = "prom/prometheus:${var.prometheus_version}"

  ports {
    internal = 9090
    external = var.prometheus_port
  }

  volumes {
    host_path      = "${var.config_path}/prometheus.yml"
    container_path = "/etc/prometheus/prometheus.yml"
    read_only      = true
  }

  volumes {
    volume_name    = "prometheus_data"
    container_path = "/prometheus"
  }

  restart = "unless-stopped"
}

resource "docker_container" "grafana" {
  name  = "ablage-${var.environment}-grafana"
  image = "grafana/grafana:${var.grafana_version}"

  ports {
    internal = 3000
    external = var.grafana_port
  }

  env = [
    "GF_SECURITY_ADMIN_PASSWORD=${var.grafana_admin_password}",
    "GF_USERS_ALLOW_SIGN_UP=false"
  ]

  volumes {
    volume_name    = "grafana_data"
    container_path = "/var/lib/grafana"
  }

  restart = "unless-stopped"
}

resource "docker_container" "loki" {
  name  = "ablage-${var.environment}-loki"
  image = "grafana/loki:${var.loki_version}"

  ports {
    internal = 3100
    external = var.loki_port
  }

  volumes {
    host_path      = "${var.config_path}/loki.yml"
    container_path = "/etc/loki/local-config.yaml"
    read_only      = true
  }

  restart = "unless-stopped"
}
```

---

## State Management

### Backend Configuration

```hcl
# backend.tf
# Remote state storage with locking

terraform {
  backend "s3" {
    bucket         = "ablage-terraform-state"
    key            = "infrastructure/terraform.tfstate"
    region         = "us-east-1"

    # Use MinIO as S3-compatible storage
    endpoint                    = "https://minio.ablage.local:9000"
    skip_credentials_validation = true
    skip_metadata_api_check     = true
    force_path_style            = true

    # State locking with DynamoDB-compatible solution
    dynamodb_table = "terraform-state-lock"
    encrypt        = true
  }
}
```

### Local Backend (Development)

```hcl
# backend.tf (development)
terraform {
  backend "local" {
    path = "terraform.tfstate"
  }
}
```

### State Migration

```bash
# Migrate from local to remote backend
terraform init -migrate-state

# Backup state before migration
cp terraform.tfstate terraform.tfstate.backup

# Verify state after migration
terraform state list
```

---

## Environment Management

### Workspace Strategy

```bash
# Create workspaces for environments
terraform workspace new dev
terraform workspace new staging
terraform workspace new production

# Switch to production workspace
terraform workspace select production

# List workspaces
terraform workspace list

# Show current workspace
terraform workspace show
```

### Environment-Specific Configuration

```hcl
# environments/production/terraform.tfvars

environment = "production"

# Compute
memory_mb  = 32768  # 32 GB
vcpu_count = 16
enable_gpu = true

# Network
network_cidr = "172.28.0.0/16"

# Storage
postgres_volume_size_gb = 500
minio_volume_size_gb    = 2000
redis_volume_size_gb    = 50
backup_volume_size_gb   = 1000

# Monitoring
prometheus_retention_days = 90
grafana_admin_password    = "${GRAFANA_ADMIN_PASSWORD}"  # From environment variable
```

### Environment Variable Pattern

```hcl
# variables.tf

variable "grafana_admin_password" {
  description = "Grafana admin password"
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.grafana_admin_password) >= 12
    error_message = "Password must be at least 12 characters."
  }
}
```

---

## Production Patterns

### 1. Immutable Infrastructure

```hcl
# Create new server, switch traffic, destroy old
resource "libvirt_domain" "ablage_server_blue" {
  count  = var.active_deployment == "blue" ? 1 : 0
  name   = "ablage-production-server-blue"
  # ... configuration
}

resource "libvirt_domain" "ablage_server_green" {
  count  = var.active_deployment == "green" ? 1 : 0
  name   = "ablage-production-server-green"
  # ... configuration
}

output "active_server_ip" {
  value = var.active_deployment == "blue" ? libvirt_domain.ablage_server_blue[0].network_interface[0].addresses[0] : libvirt_domain.ablage_server_green[0].network_interface[0].addresses[0]
}
```

### 2. Conditional Resources

```hcl
# GPU only in production
resource "null_resource" "install_nvidia_drivers" {
  count = var.environment == "production" && var.enable_gpu ? 1 : 0

  provisioner "remote-exec" {
    inline = [
      "sudo apt-get update",
      "sudo apt-get install -y nvidia-driver-${var.nvidia_driver_version}",
      "sudo reboot"
    ]
  }
}
```

### 3. Data Sources

```hcl
# Reference existing resources
data "libvirt_network" "default" {
  name = "default"
}

data "libvirt_pool" "default" {
  name = "default"
}

# Use in module
resource "libvirt_volume" "server" {
  pool = data.libvirt_pool.default.name
  # ...
}
```

---

## Security Best Practices

### 1. Sensitive Variable Handling

```hcl
# variables.tf
variable "database_password" {
  description = "PostgreSQL password"
  type        = string
  sensitive   = true  # Prevents exposure in logs
}

# Pass via environment variable
export TF_VAR_database_password="supersecret"
terraform apply
```

### 2. Secret Management Integration

```hcl
# Use Vault for secrets
data "vault_generic_secret" "database" {
  path = "secret/ablage/database"
}

resource "libvirt_domain" "ablage_server" {
  # ...

  cloudinit = templatefile("${path.module}/cloud_init.yaml", {
    db_password = data.vault_generic_secret.database.data["password"]
  })
}
```

### 3. Least Privilege

```hcl
# Create service account with minimal permissions
resource "null_resource" "service_account" {
  provisioner "local-exec" {
    command = <<-EOT
      # Create ablage user with specific permissions
      sudo useradd -r -s /bin/false ablage
      sudo usermod -aG docker ablage
    EOT
  }
}
```

---

## Terraform Commands

### Basic Workflow

```bash
# Initialize Terraform (first time)
terraform init

# Validate configuration
terraform validate

# Format code
terraform fmt -recursive

# Plan changes
terraform plan -out=tfplan

# Apply changes
terraform apply tfplan

# Destroy infrastructure
terraform destroy
```

### Advanced Commands

```bash
# Show current state
terraform show

# List resources in state
terraform state list

# Show specific resource
terraform state show module.compute.libvirt_domain.ablage_server

# Import existing resource
terraform import libvirt_domain.ablage_server ablage-production-server

# Refresh state
terraform refresh

# Output specific value
terraform output server_ip

# Generate dependency graph
terraform graph | dot -Tsvg > graph.svg
```

### Troubleshooting

```bash
# Enable debug logging
export TF_LOG=DEBUG
terraform apply

# Target specific resource
terraform apply -target=module.compute.libvirt_domain.ablage_server

# Replace resource (recreate)
terraform apply -replace=module.compute.libvirt_domain.ablage_server

# Lock/unlock state
terraform force-unlock <lock-id>
```

---

## CI/CD Integration

### GitHub Actions Workflow

```yaml
# .github/workflows/terraform.yml
name: Terraform Infrastructure

on:
  push:
    branches: [main]
    paths:
      - 'infrastructure/terraform/**'
  pull_request:
    branches: [main]
    paths:
      - 'infrastructure/terraform/**'

jobs:
  terraform:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: infrastructure/terraform

    steps:
      - uses: actions/checkout@v3

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v2
        with:
          terraform_version: 1.6.0

      - name: Terraform Format
        run: terraform fmt -check -recursive

      - name: Terraform Init
        run: terraform init

      - name: Terraform Validate
        run: terraform validate

      - name: Terraform Plan
        if: github.event_name == 'pull_request'
        run: terraform plan -no-color
        env:
          TF_VAR_database_password: ${{ secrets.DB_PASSWORD }}

      - name: Terraform Apply
        if: github.ref == 'refs/heads/main' && github.event_name == 'push'
        run: terraform apply -auto-approve
        env:
          TF_VAR_database_password: ${{ secrets.DB_PASSWORD }}
```

---

## Related Documents

- [Docker Containerization Guide](docker_containerization_guide.md)
- [Ansible Configuration Management](ansible_configuration_guide.md)
- [Infrastructure Monitoring Guide](../Monitoring/infrastructure_monitoring_guide.md)
- [Deployment Runbook](../../Execution_Layer/Runbooks/deployment_runbook.md)

---

## Revision History

| Version | Date       | Author      | Changes                       |
|---------|------------|-------------|-------------------------------|
| 1.0     | 2025-01-23 | DevOps Team | Initial Terraform guide       |

---

**"Infrastructure as Code: Version control for your data center."**

🏗️ **Infrastructure Automation Excellence Achieved!**
