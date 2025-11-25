# Terraform Infrastructure - Ablage-System OCR

Infrastructure as Code for complete Ablage-System deployment on Proxmox.

## 🚀 Quick Start

```bash
# Navigate to terraform directory
cd infrastructure/terraform

# Copy and configure variables
cp terraform.tfvars.example terraform.tfvars
nano terraform.tfvars  # Add your Proxmox credentials and configuration

# Initialize Terraform
terraform init

# Review planned changes
terraform plan

# Deploy infrastructure
terraform apply

# View outputs
terraform output
```

## 📋 Infrastructure Overview

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Load Balancer (Nginx)                    │
│                    https://domain.com                         │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              │                               │
    ┌─────────▼─────────┐         ┌──────────▼─────────┐
    │   Backend VMs      │         │   Worker VMs       │
    │   (FastAPI)        │         │   (Celery + GPU)   │
    │   • VM 1           │         │   • GPU Worker 1   │
    │   • VM 2           │         │   • GPU Worker 2   │
    └─────────┬─────────┘         └──────────┬─────────┘
              │                               │
              └───────────────┬───────────────┘
                              │
              ┌───────────────┴───────────────┐
              │                               │
    ┌─────────▼─────────┐         ┌──────────▼─────────┐
    │   PostgreSQL VM    │         │   Monitoring VM     │
    │   • Database       │         │   • Prometheus      │
    │   • Backups        │         │   • Grafana         │
    └────────────────────┘         │   • Alertmanager    │
                                   └────────────────────┘
```

### Resource Summary (Default Configuration)

- **Total VMs**: 7 (2 backend + 2 workers + 1 DB + 1 LB + 1 monitoring)
- **Total CPU Cores**: 30
- **Total RAM**: 88 GB
- **Total Storage**: ~2 TB
- **GPUs**: 2x NVIDIA RTX 4080

## 📁 Module Structure

```
terraform/
├── main.tf                    # Main infrastructure definition
├── variables.tf               # Input variables
├── outputs.tf                 # Output values
├── terraform.tfvars.example   # Example configuration
├── modules/
│   ├── networking/            # Network configuration
│   ├── compute/               # VM creation (backend/worker)
│   ├── storage/               # Storage volumes
│   ├── database/              # PostgreSQL VM
│   ├── load_balancer/         # Nginx load balancer
│   └── monitoring/            # Prometheus + Grafana
└── README.md                  # This file
```

## ⚙️ Configuration

### Required Variables

Edit `terraform.tfvars`:

```hcl
# Proxmox Configuration
proxmox_api_url      = "https://proxmox.example.com:8006/api2/json"
proxmox_user         = "root@pam"
proxmox_password     = "your_password"

# SSH Key
ssh_public_key = "ssh-rsa AAAAB3... your-email@example.com"

# Domain
domain_name = "ablage-system.example.com"
```

### Optional Customization

```hcl
# Adjust VM counts
backend_vm_count = 3  # Scale to 3 backend VMs
worker_vm_count  = 1  # Use 1 worker VM

# Adjust resources
backend_vm_cores  = 8   # More CPU
backend_vm_memory = 16384  # 16GB RAM

# Storage
minio_storage_size_gb = 1000  # 1TB for documents
```

## 🔧 Modules

### Networking Module

Configures network bridges and firewall rules for Proxmox.

**Resources**:
- Network bridge (vmbr0, vmbr1)
- Firewall rules (SSH, HTTP, HTTPS)
- Internal subnet routing

### Compute Module

Creates backend and worker VMs.

**Backend VMs**:
- FastAPI application servers
- Default: 2x 4-core, 8GB RAM, 100GB disk

**Worker VMs**:
- Celery workers with GPU passthrough
- Default: 2x 8-core, 32GB RAM, 200GB disk, 1x RTX 4080

**GPU Configuration**:
```bash
# Enable GPU passthrough in Proxmox
# Edit VM config: /etc/pve/qemu-server/<vmid>.conf
# Add: hostpci0: 01:00,pcie=1
```

### Storage Module

Configures persistent storage volumes.

**Volumes**:
- MinIO (documents): 500GB
- PostgreSQL (database): 200GB
- Backups: 1TB
- Prometheus (metrics): 100GB

### Database Module

PostgreSQL VM with optimized configuration.

**Features**:
- PostgreSQL 16
- Automated backups (daily at 2 AM)
- 30-day retention
- Performance tuning for OCR workload

### Load Balancer Module

Nginx load balancer with SSL/TLS termination.

**Features**:
- HTTP → HTTPS redirect
- SSL/TLS with Let's Encrypt
- Backend health checks
- Round-robin + least connections

### Monitoring Module

Prometheus, Grafana, and Alertmanager VM.

**Features**:
- Prometheus metrics collection
- Grafana dashboards
- Alertmanager notifications
- 30-day metrics retention

## 🚀 Deployment

### Prerequisites

1. **Proxmox VE 8.0+** installed and configured
2. **Terraform 1.6+** installed locally
3. **SSH key pair** generated
4. **Network connectivity** to Proxmox API

### Step-by-Step Deployment

#### 1. Initialize Terraform

```bash
cd infrastructure/terraform
terraform init
```

This downloads required providers (Proxmox, TLS, Local).

#### 2. Configure Variables

```bash
cp terraform.tfvars.example terraform.tfvars
nano terraform.tfvars
```

**Minimum required**:
- Proxmox credentials
- SSH public key
- Domain name

#### 3. Validate Configuration

```bash
terraform validate
```

#### 4. Review Plan

```bash
terraform plan
```

Review:
- Number of VMs to be created
- Resource allocations
- Network configuration
- Estimated costs

#### 5. Deploy Infrastructure

```bash
terraform apply
```

Type `yes` to confirm. Deployment takes ~10-15 minutes.

#### 6. Retrieve Outputs

```bash
# All outputs
terraform output

# Specific output
terraform output load_balancer_ip

# Save outputs to file
terraform output -json > outputs.json
```

## 📊 Outputs

### Application Access

- **Application URL**: `https://your-domain.com`
- **API Docs**: `https://your-domain.com/docs`
- **Grafana**: `http://monitoring-ip:3000`
- **Prometheus**: `http://monitoring-ip:9090`

### SSH Access

```bash
# Backend VMs
terraform output backend_ssh_commands

# Worker VMs
terraform output worker_ssh_commands

# Example
ssh root@10.0.2.10
```

### Database Connection

```bash
# Get connection string
terraform output database_connection_string

# Example
export DATABASE_URL="postgresql://user:password@10.0.2.20:5432/ablage_system"
```

## 🔄 Updates & Changes

### Scaling VMs

```hcl
# In terraform.tfvars
backend_vm_count = 4  # Scale from 2 to 4

# Apply changes
terraform apply
```

### Modifying Resources

```hcl
# Increase worker memory
worker_vm_memory = 65536  # 64GB

terraform apply
```

### Adding Storage

```hcl
# Increase MinIO storage
minio_storage_size_gb = 1000  # 1TB

terraform apply
```

## 🗑️ Destroying Infrastructure

### Destroy All Resources

```bash
# Review what will be destroyed
terraform plan -destroy

# Destroy infrastructure
terraform destroy

# Type 'yes' to confirm
```

### Destroy Specific Module

```bash
# Remove only worker VMs
terraform destroy -target=module.compute.proxmox_vm_qemu.worker

# Re-apply to recreate with new config
terraform apply
```

## 🐛 Troubleshooting

### Proxmox Connection Failed

```bash
# Test API connection
curl -k https://proxmox.example.com:8006/api2/json/version

# Verify credentials
cat terraform.tfvars | grep proxmox
```

### VM Creation Failed

```bash
# Check Proxmox logs
tail -f /var/log/pve/tasks/active

# Check Terraform state
terraform show

# Retry with debug logging
TF_LOG=DEBUG terraform apply
```

### GPU Passthrough Not Working

```bash
# On Proxmox host
lspci | grep -i nvidia

# Check IOMMU
dmesg | grep -i iommu

# Verify VM config
cat /etc/pve/qemu-server/<vmid>.conf | grep hostpci
```

### State Lock Error

```bash
# Force unlock (use with caution!)
terraform force-unlock <LOCK_ID>

# Or use different backend
# Edit main.tf backend configuration
```

## 🔒 Security Best Practices

### 1. Secure Proxmox Access

```bash
# Use API token instead of password
# Create token: Datacenter → Permissions → API Tokens

# In terraform.tfvars:
proxmox_api_token_id = "root@pam!terraform"
proxmox_api_token_secret = "secret-token-here"
```

### 2. Restrict SSH Access

```hcl
# In terraform.tfvars
allowed_ssh_cidrs = ["203.0.113.0/24"]  # Your IP only
```

### 3. Enable Firewall

```bash
# On each VM after deployment
ufw enable
ufw allow from 10.0.0.0/16  # Internal network
ufw allow 22  # SSH
```

### 4. Rotate Credentials

```bash
# Update Grafana password
terraform apply -var="grafana_admin_password=new_password"

# Update database password
# SSH to database VM and run:
psql -U postgres -c "ALTER USER ablage_user WITH PASSWORD 'new_password';"
```

## 📈 Cost Optimization

### Development Environment

```hcl
environment = "dev"

backend_vm_count = 1
worker_vm_count  = 1

backend_vm_cores  = 2
backend_vm_memory = 4096

minio_storage_size_gb = 100
backup_retention_days = 7
```

### Staging Environment

```hcl
environment = "staging"

backend_vm_count = 2
worker_vm_count  = 1

# Use smaller resources
prometheus_retention_days = 14
backup_retention_days = 14
```

### Production Environment

```hcl
environment = "production"

backend_vm_count = 3
worker_vm_count  = 2

# Enable all features
postgres_backup_enabled = true
alertmanager_enabled = true
backup_retention_days = 30
```

## 🔄 State Management

### Local State (Default)

```hcl
backend "local" {
  path = "terraform.tfstate"
}
```

### Remote State (Recommended for Teams)

```hcl
# S3 + DynamoDB
backend "s3" {
  bucket         = "ablage-terraform-state"
  key            = "production/terraform.tfstate"
  region         = "eu-central-1"
  encrypt        = true
  dynamodb_table = "terraform-state-lock"
}

# Or Terraform Cloud
backend "remote" {
  organization = "your-org"
  workspaces {
    name = "ablage-system-production"
  }
}
```

### Migrate State

```bash
# Backup current state
cp terraform.tfstate terraform.tfstate.backup

# Edit backend configuration in main.tf
# Initialize with new backend
terraform init -migrate-state
```

## 📚 Additional Resources

- [Terraform Proxmox Provider](https://registry.terraform.io/providers/Telmate/proxmox/latest/docs)
- [Proxmox VE Documentation](https://pve.proxmox.com/wiki/Main_Page)
- [GPU Passthrough Guide](https://pve.proxmox.com/wiki/PCI_Passthrough)
- [Terraform Best Practices](https://www.terraform.io/docs/cloud/guides/recommended-practices/index.html)

## 🆘 Support

### Common Issues

**Issue**: "Error creating VM: timeout waiting for SSH"
**Solution**: Check cloud-init configuration and network connectivity

**Issue**: "GPU not detected in worker VM"
**Solution**: Verify GPU passthrough configuration and IOMMU groups

**Issue**: "Terraform state lock timeout"
**Solution**: Use `terraform force-unlock` or check backend connectivity

### Getting Help

1. Check Terraform logs: `TF_LOG=DEBUG terraform apply`
2. Check Proxmox logs: `/var/log/pve/tasks/`
3. Review module outputs: `terraform output -json`
4. Open GitHub issue with logs and configuration (sanitized)

---

**Last Updated**: 2025-01-24
**Terraform Version**: >= 1.6.0
**Proxmox Provider Version**: ~> 2.9
**Maintainer**: Ablage-System Team
