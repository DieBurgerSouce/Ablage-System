 INFRASTRUCTURE AS CODE (IaC) GUIDE
Terraform, Ansible & Automated Infrastructure Management

📋 TABLE OF CONTENTS

Introduction & Philosophy
Terraform Configuration
Ansible Playbooks
Resource Provisioning
State Management
Multi-Environment Setup
Docker Infrastructure
GPU Server Configuration
Monitoring & Observability
Best Practices & Patterns
Troubleshooting & Recovery
Checklists & Quick Reference


1. 🎯 INTRODUCTION & PHILOSOPHY
1.1 What is Infrastructure as Code?
┌─────────────────────────────────────────────────────────┐
│         INFRASTRUCTURE AS CODE (IaC)                     │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Traditional Approach:                                  │
│  ❌ Manual server configuration                         │
│  ❌ "Click-ops" in web consoles                         │
│  ❌ Snowflake servers                                   │
│  ❌ Undocumented changes                                │
│  ❌ Hard to reproduce                                   │
│                                                         │
│  IaC Approach:                                          │
│  ✅ Infrastructure defined in code                      │
│  ✅ Version controlled (Git)                            │
│  ✅ Reproducible & consistent                           │
│  ✅ Automated deployment                                │
│  ✅ Self-documenting                                    │
│                                                         │
└─────────────────────────────────────────────────────────┘
1.2 IaC Benefits for OCR System
markdown# Benefits Specific to Your OCR Multi-Backend System

## Consistency
- GPU Backend A (DeepSeek) - Identical setup across environments
- GPU Backend B (GOT-OCR) - Same configuration dev → prod
- CPU Backend (Surya) - Reproducible server deployment

## Version Control
- Track all infrastructure changes in Git
- Rollback to previous configurations
- Review infrastructure changes like code

## Automation
- Deploy entire stack with one command
- No manual configuration errors
- Fast disaster recovery

## Documentation
- Infrastructure is the documentation
- No outdated wiki pages
- Easy onboarding for new team members

## Multi-Environment
- Dev: Local RTX 4080 setup
- Staging: Test environment
- Production: Company server + GPU server
1.3 Tool Stack Overview
yaml# infrastructure/tool_stack.yml

infrastructure_stack:
  
  # Declarative Infrastructure
  terraform:
    purpose: "Resource provisioning & management"
    use_cases:
      - "Server provisioning"
      - "Network configuration"
      - "Storage setup"
      - "DNS management"
    strengths: "Declarative, cloud-agnostic, state management"
  
  # Configuration Management
  ansible:
    purpose: "Server configuration & software installation"
    use_cases:
      - "Install PostgreSQL, Redis, Nginx"
      - "Configure GPU drivers (CUDA)"
      - "Deploy applications"
      - "User management"
    strengths: "Agentless, powerful, large ecosystem"
  
  # Containerization
  docker:
    purpose: "Application containerization"
    use_cases:
      - "Backend A (DeepSeek) container"
      - "Backend B (GOT-OCR) container"
      - "Backend C (Surya) container"
      - "PostgreSQL, Redis containers"
    strengths: "Portable, isolated, reproducible"
  
  # Secrets Management
  ansible_vault:
    purpose: "Encrypt sensitive data"
    use_cases:
      - "Database passwords"
      - "API keys"
      - "SSL certificates"
    strengths: "Git-safe, integrated with Ansible"
  
  # Version Control
  git:
    purpose: "Track infrastructure changes"
    use_cases:
      - "Version infrastructure code"
      - "Collaborate on changes"
      - "Audit trail"
    strengths: "Industry standard, branching, history"

2. 📦 TERRAFORM CONFIGURATION
2.1 Project Structure
bash# infrastructure/terraform/

terraform/
├── environments/
│   ├── dev/
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   ├── terraform.tfvars
│   │   └── outputs.tf
│   ├── staging/
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   ├── terraform.tfvars
│   │   └── outputs.tf
│   └── production/
│       ├── main.tf
│       ├── variables.tf
│       ├── terraform.tfvars
│       └── outputs.tf
├── modules/
│   ├── gpu_server/
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── outputs.tf
│   ├── cpu_server/
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── outputs.tf
│   ├── database/
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── outputs.tf
│   ├── networking/
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── outputs.tf
│   └── storage/
│       ├── main.tf
│       ├── variables.tf
│       └── outputs.tf
├── global/
│   ├── backend.tf        # Terraform state backend
│   └── versions.tf       # Provider versions
└── scripts/
    ├── init.sh
    ├── plan.sh
    └── apply.sh
2.2 GPU Server Module
hcl# terraform/modules/gpu_server/main.tf

# ============================================
# GPU SERVER FOR OCR BACKENDS
# ============================================
#
# This module provisions a GPU server for:
# - Backend A: DeepSeek-Janus-Pro
# - Backend B: GOT-OCR 2.0
#
# Requirements:
# - NVIDIA GPU (RTX 4080 or better)
# - 64GB+ RAM
# - Ubuntu 24.04
# ============================================

terraform {
  required_version = ">= 1.5.0"
  
  required_providers {
    proxmox = {
      source  = "telmate/proxmox"
      version = "~> 2.9"
    }
  }
}

# ============================================
# VARIABLES
# ============================================

variable "hostname" {
  description = "Server hostname"
  type        = string
  default     = "ocr-gpu-server"
}

variable "target_node" {
  description = "Proxmox node to create VM on"
  type        = string
}

variable "cores" {
  description = "Number of CPU cores"
  type        = number
  default     = 16
}

variable "memory" {
  description = "RAM in MB"
  type        = number
  default     = 65536  # 64GB
}

variable "disk_size" {
  description = "Disk size in GB"
  type        = string
  default     = "500G"
}

variable "gpu_pci_id" {
  description = "PCI ID of GPU to passthrough"
  type        = string
  default     = "0000:01:00"  # Adjust for your system
}

variable "ssh_keys" {
  description = "SSH public keys"
  type        = list(string)
}

variable "network_bridge" {
  description = "Network bridge"
  type        = string
  default     = "vmbr0"
}

variable "vlan_tag" {
  description = "VLAN tag (optional)"
  type        = number
  default     = null
}

# ============================================
# GPU SERVER VM
# ============================================

resource "proxmox_vm_qemu" "gpu_server" {
  name        = var.hostname
  target_node = var.target_node
  
  # VM Configuration
  cores   = var.cores
  sockets = 1
  memory  = var.memory
  
  # BIOS settings for GPU passthrough
  bios = "ovmf"
  
  # Boot settings
  boot    = "order=scsi0"
  scsihw  = "virtio-scsi-pci"
  
  # OS Disk
  disk {
    size    = var.disk_size
    type    = "scsi"
    storage = "local-lvm"
    iothread = 1
  }
  
  # Network
  network {
    model  = "virtio"
    bridge = var.network_bridge
    tag    = var.vlan_tag
  }
  
  # GPU Passthrough
  hostpci0 = "${var.gpu_pci_id},pcie=1,rombar=1"
  
  # Cloud-init
  os_type      = "cloud-init"
  ipconfig0    = "ip=dhcp"
  sshkeys      = join("\n", var.ssh_keys)
  ciuser       = "ubuntu"
  
  # Lifecycle
  lifecycle {
    prevent_destroy = true
  }
  
  # Provisioning
  provisioner "remote-exec" {
    inline = [
      "echo 'GPU Server provisioned successfully'",
      "nvidia-smi || echo 'NVIDIA drivers not yet installed'"
    ]
    
    connection {
      type        = "ssh"
      user        = "ubuntu"
      host        = self.default_ipv4_address
      private_key = file("~/.ssh/id_rsa")
    }
  }
}

# ============================================
# OUTPUTS
# ============================================

output "ip_address" {
  description = "GPU server IP address"
  value       = proxmox_vm_qemu.gpu_server.default_ipv4_address
}

output "vm_id" {
  description = "Proxmox VM ID"
  value       = proxmox_vm_qemu.gpu_server.vmid
}

output "hostname" {
  description = "Server hostname"
  value       = var.hostname
}
2.3 Database Module
hcl# terraform/modules/database/main.tf

# ============================================
# POSTGRESQL DATABASE SERVER
# ============================================

variable "hostname" {
  description = "Database server hostname"
  type        = string
  default     = "ocr-db-server"
}

variable "target_node" {
  description = "Proxmox node"
  type        = string
}

variable "cores" {
  description = "CPU cores"
  type        = number
  default     = 4
}

variable "memory" {
  description = "RAM in MB"
  type        = number
  default     = 16384  # 16GB
}

variable "disk_size" {
  description = "Disk size"
  type        = string
  default     = "200G"
}

variable "postgres_version" {
  description = "PostgreSQL version"
  type        = string
  default     = "14"
}

variable "ssh_keys" {
  description = "SSH public keys"
  type        = list(string)
}

# Database Server VM
resource "proxmox_vm_qemu" "database" {
  name        = var.hostname
  target_node = var.target_node
  
  cores   = var.cores
  sockets = 1
  memory  = var.memory
  
  disk {
    size    = var.disk_size
    type    = "scsi"
    storage = "local-lvm"
    iothread = 1
  }
  
  # Separate disk for PostgreSQL data
  disk {
    size    = "500G"
    type    = "scsi"
    storage = "local-lvm"
    iothread = 1
  }
  
  network {
    model  = "virtio"
    bridge = "vmbr0"
  }
  
  os_type = "cloud-init"
  sshkeys = join("\n", var.ssh_keys)
  
  tags = "database,postgresql"
}

output "db_ip" {
  value = proxmox_vm_qemu.database.default_ipv4_address
}
2.4 Production Environment
hcl# terraform/environments/production/main.tf

# ============================================
# PRODUCTION ENVIRONMENT
# ============================================

terraform {
  backend "s3" {
    bucket         = "ocr-terraform-state"
    key            = "production/terraform.tfstate"
    region         = "eu-central-1"
    encrypt        = true
    dynamodb_table = "terraform-locks"
  }
}

provider "proxmox" {
  pm_api_url      = var.proxmox_api_url
  pm_user         = var.proxmox_user
  pm_password     = var.proxmox_password
  pm_tls_insecure = true
}

# ============================================
# VARIABLES
# ============================================

variable "proxmox_api_url" {
  description = "Proxmox API URL"
  type        = string
}

variable "proxmox_user" {
  description = "Proxmox username"
  type        = string
}

variable "proxmox_password" {
  description = "Proxmox password"
  type        = string
  sensitive   = true
}

variable "ssh_public_keys" {
  description = "SSH public keys for servers"
  type        = list(string)
}

# ============================================
# GPU SERVER (BACKENDS A & B)
# ============================================

module "gpu_server" {
  source = "../../modules/gpu_server"
  
  hostname     = "ocr-gpu-prod"
  target_node  = "pve1"
  cores        = 16
  memory       = 65536  # 64GB
  disk_size    = "500G"
  gpu_pci_id   = "0000:01:00"
  ssh_keys     = var.ssh_public_keys
}

# ============================================
# CPU SERVER (BACKEND C - SURYA)
# ============================================

module "cpu_server" {
  source = "../../modules/cpu_server"
  
  hostname    = "ocr-cpu-prod"
  target_node = "pve2"
  cores       = 32
  memory      = 65536  # 64GB
  disk_size   = "300G"
  ssh_keys    = var.ssh_public_keys
}

# ============================================
# DATABASE SERVER
# ============================================

module "database" {
  source = "../../modules/database"
  
  hostname         = "ocr-db-prod"
  target_node      = "pve3"
  cores            = 8
  memory           = 32768  # 32GB
  disk_size        = "200G"
  postgres_version = "14"
  ssh_keys         = var.ssh_public_keys
}

# ============================================
# STORAGE (NFS/CEPH)
# ============================================

module "storage" {
  source = "../../modules/storage"
  
  hostname      = "ocr-storage-prod"
  target_node   = "pve3"
  storage_size  = "2T"
  storage_type  = "nfs"
  ssh_keys      = var.ssh_public_keys
}

# ============================================
# NETWORKING
# ============================================

module "networking" {
  source = "../../modules/networking"
  
  network_cidr     = "10.0.0.0/24"
  gpu_server_ip    = module.gpu_server.ip_address
  cpu_server_ip    = module.cpu_server.ip_address
  database_ip      = module.database.db_ip
  
  # Firewall rules
  allow_ssh_from   = ["10.0.0.0/24", "192.168.1.0/24"]
  allow_http_from  = ["0.0.0.0/0"]
  allow_https_from = ["0.0.0.0/0"]
}

# ============================================
# OUTPUTS
# ============================================

output "gpu_server_ip" {
  description = "GPU server IP address"
  value       = module.gpu_server.ip_address
}

output "cpu_server_ip" {
  description = "CPU server IP address"
  value       = module.cpu_server.ip_address
}

output "database_ip" {
  description = "Database server IP address"
  value       = module.database.db_ip
}

output "inventory_file" {
  description = "Ansible inventory content"
  value       = <<-EOT
    [gpu_servers]
    ${module.gpu_server.hostname} ansible_host=${module.gpu_server.ip_address}
    
    [cpu_servers]
    ${module.cpu_server.hostname} ansible_host=${module.cpu_server.ip_address}
    
    [databases]
    ${module.database.hostname} ansible_host=${module.database.db_ip}
    
    [all:vars]
    ansible_user=ubuntu
    ansible_ssh_private_key_file=~/.ssh/id_rsa
  EOT
}
2.5 Terraform Variables
hcl# terraform/environments/production/variables.tf

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "production"
}

variable "project_name" {
  description = "Project name"
  type        = string
  default     = "ocr-system"
}

variable "ssh_public_keys" {
  description = "SSH public keys for server access"
  type        = list(string)
  default     = [
    "ssh-rsa AAAAB3NzaC1yc2E... ben@agency"
  ]
}

variable "tags" {
  description = "Common tags for all resources"
  type        = map(string)
  default = {
    Project     = "OCR-System"
    Environment = "Production"
    ManagedBy   = "Terraform"
    Owner       = "Ben"
  }
}
hcl# terraform/environments/production/terraform.tfvars

proxmox_api_url  = "https://proxmox.company.local:8006/api2/json"
proxmox_user     = "root@pam"
proxmox_password = "stored-in-vault"  # Use Vault in production

ssh_public_keys = [
  "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQC... ben@workstation",
  "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQD... deploy@ci-server"
]

environment  = "production"
project_name = "ocr-system"
2.6 Terraform Management Scripts
bash#!/bin/bash
# terraform/scripts/tf-wrapper.sh

# ============================================
# TERRAFORM WRAPPER SCRIPT
# ============================================
#
# Usage:
#   ./tf-wrapper.sh dev init
#   ./tf-wrapper.sh dev plan
#   ./tf-wrapper.sh dev apply
#   ./tf-wrapper.sh prod destroy
#
# ============================================

set -euo pipefail

# ============================================
# CONFIGURATION
# ============================================

ENV=${1:-""}
ACTION=${2:-""}

if [ -z "$ENV" ] || [ -z "$ACTION" ]; then
    echo "Usage: $0 <environment> <action>"
    echo ""
    echo "Environments: dev, staging, production"
    echo "Actions: init, plan, apply, destroy, output"
    exit 1
fi

ENV_DIR="environments/$ENV"

if [ ! -d "$ENV_DIR" ]; then
    echo "ERROR: Environment '$ENV' not found"
    exit 1
fi

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# ============================================
# FUNCTIONS
# ============================================

log() {
    echo -e "${GREEN}[$(date '+%H:%M:%S')]${NC} $*"
}

warn() {
    echo -e "${YELLOW}[WARNING]${NC} $*"
}

error() {
    echo -e "${RED}[ERROR]${NC} $*"
    exit 1
}

confirm() {
    read -p "Continue? (yes/no): " response
    if [ "$response" != "yes" ]; then
        echo "Aborted"
        exit 0
    fi
}

# ============================================
# ENVIRONMENT CHECKS
# ============================================

log "Environment: $ENV"
log "Action: $ACTION"

cd "$ENV_DIR"

# Check for required files
if [ ! -f "main.tf" ]; then
    error "main.tf not found in $ENV_DIR"
fi

# ============================================
# EXECUTE ACTION
# ============================================

case "$ACTION" in
    init)
        log "Initializing Terraform..."
        terraform init -upgrade
        ;;
    
    plan)
        log "Creating execution plan..."
        terraform plan -out=tfplan
        ;;
    
    apply)
        if [ ! -f "tfplan" ]; then
            warn "No plan file found. Run 'plan' first."
            log "Creating plan..."
            terraform plan -out=tfplan
        fi
        
        log "Reviewing plan..."
        terraform show tfplan
        
        if [ "$ENV" == "production" ]; then
            warn "⚠️  You are about to apply changes to PRODUCTION!"
            confirm
        fi
        
        log "Applying changes..."
        terraform apply tfplan
        
        # Cleanup plan file
        rm -f tfplan
        ;;
    
    destroy)
        error_msg="⚠️  DANGER: You are about to DESTROY $ENV infrastructure!"
        
        if [ "$ENV" == "production" ]; then
            error "$error_msg This is PRODUCTION!"
        else
            warn "$error_msg"
        fi
        
        confirm
        
        log "Destroying infrastructure..."
        terraform destroy
        ;;
    
    output)
        log "Terraform outputs:"
        terraform output
        ;;
    
    validate)
        log "Validating configuration..."
        terraform validate
        terraform fmt -check -recursive
        ;;
    
    *)
        error "Unknown action: $ACTION"
        ;;
esac

log "Done!"

3. 🔧 ANSIBLE PLAYBOOKS
3.1 Ansible Project Structure
bash# infrastructure/ansible/

ansible/
├── inventory/
│   ├── production/
│   │   ├── hosts.yml
│   │   └── group_vars/
│   │       ├── all.yml
│   │       ├── gpu_servers.yml
│   │       ├── cpu_servers.yml
│   │       └── databases.yml
│   ├── staging/
│   │   └── hosts.yml
│   └── dev/
│       └── hosts.yml
├── playbooks/
│   ├── site.yml                  # Main playbook
│   ├── gpu_server.yml            # GPU server setup
│   ├── cpu_server.yml            # CPU server setup
│   ├── database.yml              # Database setup
│   ├── deploy_backends.yml       # Deploy OCR backends
│   └── monitoring.yml            # Setup monitoring
├── roles/
│   ├── common/
│   │   ├── tasks/
│   │   ├── handlers/
│   │   ├── templates/
│   │   └── files/
│   ├── nvidia_drivers/
│   ├── docker/
│   ├── postgresql/
│   ├── redis/
│   ├── nginx/
│   ├── prometheus/
│   └── ocr_backends/
├── group_vars/
│   └── all.yml
├── host_vars/
├── files/
├── templates/
├── ansible.cfg
└── requirements.yml
3.2 Ansible Configuration
ini# ansible/ansible.cfg

[defaults]
inventory = inventory/production/hosts.yml
remote_user = ubuntu
host_key_checking = False
timeout = 30
gathering = smart
fact_caching = jsonfile
fact_caching_connection = /tmp/ansible_facts
fact_caching_timeout = 3600

# Privilege escalation
become = True
become_method = sudo
become_user = root
become_ask_pass = False

# SSH
private_key_file = ~/.ssh/id_rsa
ssh_args = -o ControlMaster=auto -o ControlPersist=60s

# Logging
log_path = ./ansible.log

# Performance
forks = 10
pipelining = True

# Roles
roles_path = ./roles

# Vault
vault_password_file = .vault_pass

[inventory]
enable_plugins = yaml, ini, auto

[ssh_connection]
ssh_args = -C -o ControlMaster=auto -o ControlPersist=60s
pipelining = True
3.3 Inventory File
yaml# ansible/inventory/production/hosts.yml

all:
  children:
    gpu_servers:
      hosts:
        ocr-gpu-prod:
          ansible_host: 10.0.0.10
          gpu_type: rtx_4080
          gpu_memory: 16384
          cuda_version: "12.1"
    
    cpu_servers:
      hosts:
        ocr-cpu-prod:
          ansible_host: 10.0.0.20
          cpu_cores: 32
          memory_mb: 65536
    
    databases:
      hosts:
        ocr-db-prod:
          ansible_host: 10.0.0.30
          postgres_version: "14"
          max_connections: 200
    
    loadbalancers:
      hosts:
        ocr-lb-prod:
          ansible_host: 10.0.0.5
          nginx_version: "1.24"
  
  vars:
    ansible_user: ubuntu
    ansible_ssh_private_key_file: ~/.ssh/id_rsa
    ansible_python_interpreter: /usr/bin/python3
    
    # Environment
    environment_name: production
    project_name: ocr-system
    
    # Network
    network_cidr: "10.0.0.0/24"
    dns_servers:
      - "8.8.8.8"
      - "8.8.4.4"
3.4 GPU Server Playbook
yaml# ansible/playbooks/gpu_server.yml

---
- name: Configure GPU Server for OCR Backends
  hosts: gpu_servers
  become: yes
  
  vars:
    nvidia_driver_version: "535"
    cuda_version: "12.1"
    docker_version: "24.0"
    
  tasks:
    
    # ========================================
    # SYSTEM UPDATES
    # ========================================
    
    - name: Update apt cache
      apt:
        update_cache: yes
        cache_valid_time: 3600
    
    - name: Upgrade all packages
      apt:
        upgrade: dist
        autoremove: yes
    
    # ========================================
    # NVIDIA DRIVERS
    # ========================================
    
    - name: Add NVIDIA driver PPA
      apt_repository:
        repo: ppa:graphics-drivers/ppa
        state: present
    
    - name: Install NVIDIA driver
      apt:
        name: "nvidia-driver-{{ nvidia_driver_version }}"
        state: present
      notify: reboot_server
    
    - name: Check NVIDIA driver
      command: nvidia-smi
      register: nvidia_check
      changed_when: false
      failed_when: false
    
    - name: Display NVIDIA info
      debug:
        msg: "{{ nvidia_check.stdout_lines }}"
      when: nvidia_check.rc == 0
    
    # ========================================
    # CUDA TOOLKIT
    # ========================================
    
    - name: Download CUDA toolkit installer
      get_url:
        url: "https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/cuda-keyring_1.1-1_all.deb"
        dest: /tmp/cuda-keyring.deb
    
    - name: Install CUDA keyring
      apt:
        deb: /tmp/cuda-keyring.deb
    
    - name: Install CUDA toolkit
      apt:
        name: "cuda-toolkit-{{ cuda_version | replace('.', '-') }}"
        state: present
        update_cache: yes
    
    - name: Add CUDA to PATH
      lineinfile:
        path: /etc/environment
        regexp: '^PATH='
        line: 'PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/local/cuda/bin"'
    
    - name: Configure LD_LIBRARY_PATH
      copy:
        dest: /etc/ld.so.conf.d/cuda.conf
        content: |
          /usr/local/cuda/lib64
          /usr/local/cuda/extras/CUPTI/lib64
      notify: run_ldconfig
    
    # ========================================
    # DOCKER WITH NVIDIA RUNTIME
    # ========================================
    
    - name: Install Docker dependencies
      apt:
        name:
          - apt-transport-https
          - ca-certificates
          - curl
          - gnupg
          - lsb-release
        state: present
    
    - name: Add Docker GPG key
      apt_key:
        url: https://download.docker.com/linux/ubuntu/gpg
        state: present
    
    - name: Add Docker repository
      apt_repository:
        repo: "deb [arch=amd64] https://download.docker.com/linux/ubuntu {{ ansible_distribution_release }} stable"
        state: present
    
    - name: Install Docker
      apt:
        name:
          - docker-ce
          - docker-ce-cli
          - containerd.io
          - docker-compose-plugin
        state: present
        update_cache: yes
    
    - name: Install NVIDIA Container Toolkit
      block:
        - name: Add NVIDIA Container Toolkit GPG key
          apt_key:
            url: https://nvidia.github.io/libnvidia-container/gpgkey
            state: present
        
        - name: Add NVIDIA Container Toolkit repository
          apt_repository:
            repo: "deb https://nvidia.github.io/libnvidia-container/stable/ubuntu{{ ansible_distribution_version }}/$(ARCH) /"
            state: present
        
        - name: Install nvidia-container-toolkit
          apt:
            name: nvidia-container-toolkit
            state: present
            update_cache: yes
        
        - name: Configure Docker to use NVIDIA runtime
          copy:
            dest: /etc/docker/daemon.json
            content: |
              {
                "runtimes": {
                  "nvidia": {
                    "path": "nvidia-container-runtime",
                    "runtimeArgs": []
                  }
                },
                "default-runtime": "nvidia"
              }
          notify: restart_docker
    
    # ========================================
    # PYTHON & DEPENDENCIES
    # ========================================
    
    - name: Install Python and pip
      apt:
        name:
          - python3
          - python3-pip
          - python3-venv
        state: present
    
    - name: Install PyTorch with CUDA support
      pip:
        name:
          - torch
          - torchvision
          - torchaudio
        extra_args: "--index-url https://download.pytorch.org/whl/cu121"
        executable: pip3
    
    # ========================================
    # MONITORING
    # ========================================
    
    - name: Install nvidia_gpu_exporter for Prometheus
      get_url:
        url: https://github.com/utkuozdemir/nvidia_gpu_exporter/releases/download/v1.1.0/nvidia_gpu_exporter_1.1.0_linux_x86_64.tar.gz
        dest: /tmp/nvidia_exporter.tar.gz
    
    - name: Extract nvidia_gpu_exporter
      unarchive:
        src: /tmp/nvidia_exporter.tar.gz
        dest: /usr/local/bin/
        remote_src: yes
    
    - name: Create nvidia_exporter systemd service
      copy:
        dest: /etc/systemd/system/nvidia_exporter.service
        content: |
          [Unit]
          Description=NVIDIA GPU Prometheus Exporter
          After=network.target
          
          [Service]
          Type=simple
          User=nobody
          ExecStart=/usr/local/bin/nvidia_gpu_exporter
          Restart=on-failure
          
          [Install]
          WantedBy=multi-user.target
      notify: reload_systemd
    
    - name: Enable and start nvidia_exporter
      systemd:
        name: nvidia_exporter
        enabled: yes
        state: started
  
  # ========================================
  # HANDLERS
  # ========================================
  
  handlers:
    - name: reboot_server
      reboot:
        reboot_timeout: 600
    
    - name: run_ldconfig
      command: ldconfig
    
    - name: restart_docker
      systemd:
        name: docker
        state: restarted
    
    - name: reload_systemd
      systemd:
        daemon_reload: yes
3.5 Database Playbook
yaml# ansible/playbooks/database.yml

---
- name: Configure PostgreSQL Database Server
  hosts: databases
  become: yes
  
  vars:
    postgres_version: "14"
    postgres_data_dir: "/var/lib/postgresql/{{ postgres_version }}/main"
    postgres_max_connections: 200
    postgres_shared_buffers: "8GB"
    postgres_effective_cache_size: "24GB"
    postgres_work_mem: "64MB"
    
  tasks:
    
    # ========================================
    # INSTALL POSTGRESQL
    # ========================================
    
    - name: Add PostgreSQL APT repository
      apt:
        deb: https://apt.postgresql.org/pub/repos/apt/pool/main/p/postgresql-common/postgresql-common_256.pgdg24.04+1_all.deb
        state: present
    
    - name: Install PostgreSQL
      apt:
        name:
          - "postgresql-{{ postgres_version }}"
          - "postgresql-contrib-{{ postgres_version }}"
          - postgresql-client
          - python3-psycopg2
        state: present
        update_cache: yes
    
    # ========================================
    # CONFIGURE POSTGRESQL
    # ========================================
    
    - name: Configure postgresql.conf
      template:
        src: templates/postgresql.conf.j2
        dest: "/etc/postgresql/{{ postgres_version }}/main/postgresql.conf"
        owner: postgres
        group: postgres
        mode: '0644'
      notify: restart_postgresql
    
    - name: Configure pg_hba.conf
      template:
        src: templates/pg_hba.conf.j2
        dest: "/etc/postgresql/{{ postgres_version }}/main/pg_hba.conf"
        owner: postgres
        group: postgres
        mode: '0640'
      notify: restart_postgresql
    
    # ========================================
    # CREATE DATABASE & USER
    # ========================================
    
    - name: Create OCR database
      postgresql_db:
        name: ocr_production
        encoding: UTF-8
        lc_collate: en_US.UTF-8
        lc_ctype: en_US.UTF-8
        template: template0
      become_user: postgres
    
    - name: Create OCR database user
      postgresql_user:
        name: ocr_user
        password: "{{ vault_postgres_password }}"
        role_attr_flags: LOGIN
      become_user: postgres
    
    - name: Grant privileges to OCR user
      postgresql_privs:
        database: ocr_production
        role: ocr_user
        privs: ALL
        type: database
      become_user: postgres
    
    # ========================================
    # EXTENSIONS
    # ========================================
    
    - name: Enable PostgreSQL extensions
      postgresql_ext:
        name: "{{ item }}"
        db: ocr_production
      become_user: postgres
      loop:
        - pg_stat_statements
        - pg_trgm
        - uuid-ossp
    
    # ========================================
    # WAL ARCHIVING (FOR PITR)
    # ========================================
    
    - name: Create WAL archive directory
      file:
        path: /var/backups/postgres/wal
        state: directory
        owner: postgres
        group: postgres
        mode: '0750'
    
    - name: Configure WAL archiving
      lineinfile:
        path: "/etc/postgresql/{{ postgres_version }}/main/postgresql.conf"
        regexp: "{{ item.regexp }}"
        line: "{{ item.line }}"
      loop:
        - {regexp: '^#?wal_level', line: 'wal_level = replica'}
        - {regexp: '^#?archive_mode', line: 'archive_mode = on'}
        - {regexp: '^#?archive_command', line: "archive_command = 'test ! -f /var/backups/postgres/wal/%f && cp %p /var/backups/postgres/wal/%f'"}
      notify: restart_postgresql
    
    # ========================================
    # MONITORING
    # ========================================
    
    - name: Install postgres_exporter
      get_url:
        url: https://github.com/prometheus-community/postgres_exporter/releases/download/v0.15.0/postgres_exporter-0.15.0.linux-amd64.tar.gz
        dest: /tmp/postgres_exporter.tar.gz
    
    - name: Extract postgres_exporter
      unarchive:
        src: /tmp/postgres_exporter.tar.gz
        dest: /usr/local/bin/
        remote_src: yes
        extra_opts: [--strip-components=1]
    
    - name: Create postgres_exporter service
      copy:
        dest: /etc/systemd/system/postgres_exporter.service
        content: |
          [Unit]
          Description=PostgreSQL Prometheus Exporter
          After=postgresql.service
          
          [Service]
          Type=simple
          User=postgres
          Environment="DATA_SOURCE_NAME=postgresql://postgres@localhost:5432/postgres?sslmode=disable"
          ExecStart=/usr/local/bin/postgres_exporter
          Restart=on-failure
          
          [Install]
          WantedBy=multi-user.target
      notify: reload_systemd
    
    - name: Enable postgres_exporter
      systemd:
        name: postgres_exporter
        enabled: yes
        state: started
  
  handlers:
    - name: restart_postgresql
      systemd:
        name: postgresql
        state: restarted
    
    - name: reload_systemd
      systemd:
        daemon_reload: yes
3.6 Deploy OCR Backends Playbook
yaml# ansible/playbooks/deploy_backends.yml

---
- name: Deploy OCR Backend Services
  hosts: gpu_servers
  become: yes
  
  vars:
    docker_compose_version: "2.23.0"
    project_dir: "/opt/ocr-system"
    
  tasks:
    
    # ========================================
    # PREPARE DEPLOYMENT
    # ========================================
    
    - name: Create project directory
      file:
        path: "{{ project_dir }}"
        state: directory
        owner: ubuntu
        group: ubuntu
        mode: '0755'
    
    - name: Copy Docker Compose file
      template:
        src: templates/docker-compose.gpu.yml.j2
        dest: "{{ project_dir }}/docker-compose.yml"
        owner: ubuntu
        group: ubuntu
        mode: '0644'
    
    - name: Copy environment file
      template:
        src: templates/.env.j2
        dest: "{{ project_dir }}/.env"
        owner: ubuntu
        group: ubuntu
        mode: '0600'
    
    # ========================================
    # DEPLOY SERVICES
    # ========================================
    
    - name: Pull Docker images
      community.docker.docker_compose:
        project_src: "{{ project_dir }}"
        pull: yes
      register: pull_output
    
    - name: Start OCR backend services
      community.docker.docker_compose:
        project_src: "{{ project_dir }}"
        state: present
        restarted: yes
      register: deploy_output
    
    - name: Wait for services to be healthy
      wait_for:
        host: localhost
        port: "{{ item }}"
        delay: 10
        timeout: 300
      loop:
        - 8001  # Backend A (DeepSeek)
        - 8002  # Backend B (GOT-OCR)
    
    # ========================================
    # HEALTH CHECKS
    # ========================================
    
    - name: Check Backend A health
      uri:
        url: http://localhost:8001/health
        status_code: 200
      register: backend_a_health
      retries: 5
      delay: 10
    
    - name: Check Backend B health
      uri:
        url: http://localhost:8002/health
        status_code: 200
      register: backend_b_health
      retries: 5
      delay: 10
    
    - name: Display deployment status
      debug:
        msg:
          - "Backend A (DeepSeek): {{ 'HEALTHY' if backend_a_health.status == 200 else 'UNHEALTHY' }}"
          - "Backend B (GOT-OCR): {{ 'HEALTHY' if backend_b_health.status == 200 else 'UNHEALTHY' }}"




INFRASTRUCTURE AS CODE (IaC) GUIDE - TEIL 2

4. 🚀 RESOURCE PROVISIONING
4.1 Complete Provisioning Workflow
bash#!/bin/bash
# scripts/provision_infrastructure.sh

# ============================================
# COMPLETE INFRASTRUCTURE PROVISIONING
# ============================================
#
# This script orchestrates the complete
# infrastructure provisioning workflow:
# 1. Terraform: Provision servers
# 2. Ansible: Configure servers
# 3. Docker: Deploy applications
# 4. Validate: Health checks
#
# Usage:
#   ./provision_infrastructure.sh dev
#   ./provision_infrastructure.sh production
#
# ============================================

set -euo pipefail

# ============================================
# CONFIGURATION
# ============================================

ENVIRONMENT=${1:-"dev"}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ============================================
# FUNCTIONS
# ============================================

log() {
    echo -e "${GREEN}[$(date '+%H:%M:%S')]${NC} $*"
}

log_step() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}▶ $*${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

error() {
    echo -e "${RED}[ERROR]${NC} $*"
    exit 1
}

warn() {
    echo -e "${YELLOW}[WARNING]${NC} $*"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $*"
}

# ============================================
# VALIDATION
# ============================================

log_step "STEP 1: Pre-flight Checks"

# Check environment
if [ "$ENVIRONMENT" != "dev" ] && [ "$ENVIRONMENT" != "staging" ] && [ "$ENVIRONMENT" != "production" ]; then
    error "Invalid environment: $ENVIRONMENT. Must be dev, staging, or production"
fi

log "Environment: $ENVIRONMENT"

# Check required tools
log "Checking required tools..."
REQUIRED_TOOLS=("terraform" "ansible" "docker" "jq")

for tool in "${REQUIRED_TOOLS[@]}"; do
    if ! command -v "$tool" &> /dev/null; then
        error "$tool is not installed"
    else
        VERSION=$(command "$tool" --version | head -n1)
        log "  ✓ $tool: $VERSION"
    fi
done

# Check credentials
log "Checking credentials..."
if [ "$ENVIRONMENT" == "production" ]; then
    if [ -z "${PROXMOX_PASSWORD:-}" ]; then
        error "PROXMOX_PASSWORD environment variable not set"
    fi
    log "  ✓ Proxmox credentials present"
fi

# ============================================
# TERRAFORM PROVISIONING
# ============================================

log_step "STEP 2: Terraform - Provision Infrastructure"

cd "$PROJECT_ROOT/terraform/environments/$ENVIRONMENT"

log "Initializing Terraform..."
terraform init -upgrade

log "Creating execution plan..."
terraform plan -out=tfplan

if [ "$ENVIRONMENT" == "production" ]; then
    warn "⚠️  About to provision PRODUCTION infrastructure!"
    read -p "Continue? (yes/no): " CONFIRM
    if [ "$CONFIRM" != "yes" ]; then
        error "Provisioning cancelled"
    fi
fi

log "Applying infrastructure changes..."
terraform apply tfplan

rm -f tfplan

log "Extracting outputs..."
terraform output -json > "$PROJECT_ROOT/outputs/terraform_outputs.json"

# Extract IPs
GPU_SERVER_IP=$(terraform output -raw gpu_server_ip)
CPU_SERVER_IP=$(terraform output -raw cpu_server_ip)
DB_SERVER_IP=$(terraform output -raw database_ip)

log "Infrastructure provisioned:"
log "  GPU Server: $GPU_SERVER_IP"
log "  CPU Server: $CPU_SERVER_IP"
log "  Database:   $DB_SERVER_IP"

# Generate Ansible inventory
log "Generating Ansible inventory..."
terraform output -raw inventory_file > "$PROJECT_ROOT/ansible/inventory/$ENVIRONMENT/hosts.yml"

success "Infrastructure provisioned successfully"

# ============================================
# WAIT FOR SERVERS
# ============================================

log_step "STEP 3: Wait for Servers to Boot"

wait_for_ssh() {
    local host=$1
    local max_attempts=30
    local attempt=0
    
    log "Waiting for SSH on $host..."
    
    while [ $attempt -lt $max_attempts ]; do
        if ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no ubuntu@"$host" "echo 'SSH ready'" &>/dev/null; then
            log "  ✓ SSH ready on $host"
            return 0
        fi
        
        attempt=$((attempt + 1))
        sleep 10
    done
    
    error "SSH not available on $host after $max_attempts attempts"
}

wait_for_ssh "$GPU_SERVER_IP"
wait_for_ssh "$CPU_SERVER_IP"
wait_for_ssh "$DB_SERVER_IP"

success "All servers are accessible via SSH"

# ============================================
# ANSIBLE CONFIGURATION
# ============================================

log_step "STEP 4: Ansible - Configure Servers"

cd "$PROJECT_ROOT/ansible"

log "Running Ansible playbook: site.yml"
ansible-playbook \
    -i "inventory/$ENVIRONMENT/hosts.yml" \
    playbooks/site.yml \
    --extra-vars "environment=$ENVIRONMENT" \
    | tee "$PROJECT_ROOT/logs/ansible_${ENVIRONMENT}_$(date +%Y%m%d_%H%M%S).log"

if [ ${PIPESTATUS[0]} -eq 0 ]; then
    success "Server configuration completed"
else
    error "Ansible playbook failed"
fi

# ============================================
# DEPLOY APPLICATIONS
# ============================================

log_step "STEP 5: Deploy OCR Backend Applications"

log "Deploying GPU backends (DeepSeek + GOT-OCR)..."
ansible-playbook \
    -i "inventory/$ENVIRONMENT/hosts.yml" \
    playbooks/deploy_backends.yml \
    --tags gpu \
    --extra-vars "environment=$ENVIRONMENT"

log "Deploying CPU backend (Surya)..."
ansible-playbook \
    -i "inventory/$ENVIRONMENT/hosts.yml" \
    playbooks/deploy_backends.yml \
    --tags cpu \
    --extra-vars "environment=$ENVIRONMENT"

success "Applications deployed"

# ============================================
# HEALTH CHECKS
# ============================================

log_step "STEP 6: Health Checks"

health_check() {
    local name=$1
    local url=$2
    local max_attempts=10
    local attempt=0
    
    log "Checking $name..."
    
    while [ $attempt -lt $max_attempts ]; do
        if curl -sf "$url" > /dev/null; then
            log "  ✓ $name is healthy"
            return 0
        fi
        
        attempt=$((attempt + 1))
        sleep 10
    done
    
    warn "$name health check failed"
    return 1
}

health_check "Backend A (DeepSeek)" "http://$GPU_SERVER_IP:8001/health"
health_check "Backend B (GOT-OCR)" "http://$GPU_SERVER_IP:8002/health"
health_check "Backend C (Surya)" "http://$CPU_SERVER_IP:8003/health"
health_check "Database" "http://$DB_SERVER_IP:5432"

# ============================================
# SUMMARY
# ============================================

log_step "PROVISIONING COMPLETE!"

cat << EOF

╔════════════════════════════════════════════════════════════╗
║           INFRASTRUCTURE PROVISIONING SUMMARY              ║
╠════════════════════════════════════════════════════════════╣
║                                                            ║
║  Environment:  $ENVIRONMENT                                        ║
║                                                            ║
║  GPU Server:   $GPU_SERVER_IP                            ║
║    ├─ Backend A (DeepSeek)  → http://$GPU_SERVER_IP:8001 ║
║    └─ Backend B (GOT-OCR)   → http://$GPU_SERVER_IP:8002 ║
║                                                            ║
║  CPU Server:   $CPU_SERVER_IP                            ║
║    └─ Backend C (Surya)     → http://$CPU_SERVER_IP:8003 ║
║                                                            ║
║  Database:     $DB_SERVER_IP                             ║
║    └─ PostgreSQL 14         → postgresql://$DB_SERVER_IP:5432 ║
║                                                            ║
║  Next Steps:                                               ║
║  1. Configure DNS/load balancer                            ║
║  2. Set up monitoring dashboards                           ║
║  3. Run integration tests                                  ║
║  4. Update documentation                                   ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝

EOF

log "Provisioning completed in $(($SECONDS / 60)) minutes and $(($SECONDS % 60)) seconds"
4.2 Resource Templates
yaml# templates/resource_specifications.yml

# ============================================
# RESOURCE SPECIFICATIONS
# ============================================
#
# This file defines resource requirements
# for different components of the OCR system
#
# ============================================

gpu_server:
  name: "GPU Server (Backends A & B)"
  purpose: "DeepSeek-Janus-Pro + GOT-OCR 2.0"
  
  minimum_specs:
    cpu_cores: 8
    memory_gb: 32
    gpu_model: "NVIDIA RTX 3080"
    gpu_memory_gb: 10
    disk_gb: 250
  
  recommended_specs:
    cpu_cores: 16
    memory_gb: 64
    gpu_model: "NVIDIA RTX 4080"
    gpu_memory_gb: 16
    disk_gb: 500
  
  optimal_specs:
    cpu_cores: 24
    memory_gb: 128
    gpu_model: "NVIDIA RTX 4090"
    gpu_memory_gb: 24
    disk_gb: 1000
  
  software_requirements:
    - Ubuntu 24.04 LTS
    - NVIDIA Driver 535+
    - CUDA 12.1+
    - Docker 24.0+
    - NVIDIA Container Toolkit

cpu_server:
  name: "CPU Server (Backend C)"
  purpose: "Surya + Docling (Fallback)"
  
  minimum_specs:
    cpu_cores: 16
    memory_gb: 32
    disk_gb: 200
  
  recommended_specs:
    cpu_cores: 32
    memory_gb: 64
    disk_gb: 300
  
  optimal_specs:
    cpu_cores: 64
    memory_gb: 128
    disk_gb: 500
  
  software_requirements:
    - Ubuntu 24.04 LTS
    - Python 3.11+
    - Docker 24.0+

database_server:
  name: "Database Server"
  purpose: "PostgreSQL for OCR metadata"
  
  minimum_specs:
    cpu_cores: 4
    memory_gb: 8
    disk_gb: 100
    disk_iops: 3000
  
  recommended_specs:
    cpu_cores: 8
    memory_gb: 32
    disk_gb: 200
    disk_iops: 6000
  
  optimal_specs:
    cpu_cores: 16
    memory_gb: 64
    disk_gb: 500
    disk_iops: 10000
  
  software_requirements:
    - Ubuntu 24.04 LTS
    - PostgreSQL 14+
    - pgBouncer

storage_server:
  name: "Storage Server"
  purpose: "Document storage (NFS/Ceph)"
  
  minimum_specs:
    cpu_cores: 4
    memory_gb: 16
    disk_gb: 1000
  
  recommended_specs:
    cpu_cores: 8
    memory_gb: 32
    disk_gb: 5000
  
  optimal_specs:
    cpu_cores: 16
    memory_gb: 64
    disk_gb: 10000
  
  software_requirements:
    - Ubuntu 24.04 LTS
    - NFS Server or Ceph

loadbalancer:
  name: "Load Balancer"
  purpose: "Nginx reverse proxy"
  
  minimum_specs:
    cpu_cores: 2
    memory_gb: 4
    disk_gb: 50
  
  recommended_specs:
    cpu_cores: 4
    memory_gb: 8
    disk_gb: 100
  
  software_requirements:
    - Ubuntu 24.04 LTS
    - Nginx 1.24+
    - Certbot (Let's Encrypt)
4.3 Network Configuration
hcl# terraform/modules/networking/main.tf

# ============================================
# NETWORK CONFIGURATION MODULE
# ============================================

variable "network_cidr" {
  description = "Network CIDR block"
  type        = string
  default     = "10.0.0.0/24"
}

variable "gpu_server_ip" {
  description = "GPU server IP"
  type        = string
}

variable "cpu_server_ip" {
  description = "CPU server IP"
  type        = string
}

variable "database_ip" {
  description = "Database IP"
  type        = string
}

variable "allow_ssh_from" {
  description = "CIDR blocks allowed to SSH"
  type        = list(string)
  default     = ["10.0.0.0/24"]
}

# ============================================
# FIREWALL RULES
# ============================================

# GPU Server Firewall
resource "null_resource" "gpu_server_firewall" {
  provisioner "remote-exec" {
    inline = [
      # Install UFW
      "sudo apt-get update",
      "sudo apt-get install -y ufw",
      
      # Default policies
      "sudo ufw default deny incoming",
      "sudo ufw default allow outgoing",
      
      # SSH (from specific networks)
      "sudo ufw allow from 10.0.0.0/24 to any port 22",
      "sudo ufw allow from 192.168.1.0/24 to any port 22",
      
      # API endpoints (internal only)
      "sudo ufw allow from 10.0.0.0/24 to any port 8001",
      "sudo ufw allow from 10.0.0.0/24 to any port 8002",
      
      # Prometheus metrics
      "sudo ufw allow from 10.0.0.0/24 to any port 9100",
      "sudo ufw allow from 10.0.0.0/24 to any port 9400", # nvidia_exporter
      
      # Enable firewall
      "sudo ufw --force enable",
      
      # Show status
      "sudo ufw status verbose"
    ]
    
    connection {
      type        = "ssh"
      user        = "ubuntu"
      host        = var.gpu_server_ip
      private_key = file("~/.ssh/id_rsa")
    }
  }
}

# Database Firewall
resource "null_resource" "database_firewall" {
  provisioner "remote-exec" {
    inline = [
      "sudo apt-get update",
      "sudo apt-get install -y ufw",
      "sudo ufw default deny incoming",
      "sudo ufw default allow outgoing",
      
      # SSH
      "sudo ufw allow from 10.0.0.0/24 to any port 22",
      
      # PostgreSQL (only from app servers)
      "sudo ufw allow from ${var.gpu_server_ip} to any port 5432",
      "sudo ufw allow from ${var.cpu_server_ip} to any port 5432",
      
      # Prometheus metrics
      "sudo ufw allow from 10.0.0.0/24 to any port 9187", # postgres_exporter
      
      "sudo ufw --force enable"
    ]
    
    connection {
      type        = "ssh"
      user        = "ubuntu"
      host        = var.database_ip
      private_key = file("~/.ssh/id_rsa")
    }
  }
}

# ============================================
# DNS CONFIGURATION (Optional)
# ============================================

# If using cloud provider DNS
resource "null_resource" "configure_dns" {
  provisioner "local-exec" {
    command = <<-EOT
      echo "GPU Server: ${var.gpu_server_ip}" >> /etc/hosts
      echo "CPU Server: ${var.cpu_server_ip}" >> /etc/hosts
      echo "Database: ${var.database_ip}" >> /etc/hosts
    EOT
  }
}

# ============================================
# OUTPUTS
# ============================================

output "network_config" {
  value = {
    network_cidr  = var.network_cidr
    gpu_server_ip = var.gpu_server_ip
    cpu_server_ip = var.cpu_server_ip
    database_ip   = var.database_ip
  }
}

5. 💾 STATE MANAGEMENT
5.1 Terraform State Backend
hcl# terraform/global/backend.tf

# ============================================
# TERRAFORM STATE BACKEND CONFIGURATION
# ============================================
#
# This configures remote state storage with:
# - S3 for state files
# - DynamoDB for state locking
# - Encryption at rest
#
# Benefits:
# - Team collaboration
# - State locking prevents conflicts
# - Version history
# - Secure storage
#
# ============================================

terraform {
  backend "s3" {
    # S3 bucket for state files
    bucket = "ocr-terraform-state"
    
    # State file path within bucket
    key = "global/terraform.tfstate"
    
    # AWS region
    region = "eu-central-1"
    
    # Encryption
    encrypt = true
    
    # DynamoDB table for state locking
    dynamodb_table = "terraform-locks"
    
    # Versioning (recommended)
    # Enable versioning on S3 bucket to keep history
  }
}

# ============================================
# ALTERNATIVE: Local State (Development)
# ============================================

# For development, you can use local state:
# terraform {
#   backend "local" {
#     path = "terraform.tfstate"
#   }
# }

# ============================================
# ALTERNATIVE: Terraform Cloud
# ============================================

# For Terraform Cloud:
# terraform {
#   cloud {
#     organization = "your-org"
#     workspaces {
#       name = "ocr-production"
#     }
#   }
# }
5.2 State Backend Setup
bash#!/bin/bash
# scripts/setup_state_backend.sh

# ============================================
# SETUP TERRAFORM STATE BACKEND
# ============================================
#
# Creates S3 bucket and DynamoDB table for
# Terraform remote state management
#
# ============================================

set -euo pipefail

# Configuration
BUCKET_NAME="ocr-terraform-state"
DYNAMODB_TABLE="terraform-locks"
REGION="eu-central-1"

log() {
    echo "[$(date '+%H:%M:%S')] $*"
}

# ============================================
# CREATE S3 BUCKET
# ============================================

log "Creating S3 bucket for Terraform state..."

aws s3api create-bucket \
    --bucket "$BUCKET_NAME" \
    --region "$REGION" \
    --create-bucket-configuration LocationConstraint="$REGION" \
    2>/dev/null || log "Bucket already exists"

# Enable versioning
log "Enabling versioning..."
aws s3api put-bucket-versioning \
    --bucket "$BUCKET_NAME" \
    --versioning-configuration Status=Enabled

# Enable encryption
log "Enabling encryption..."
aws s3api put-bucket-encryption \
    --bucket "$BUCKET_NAME" \
    --server-side-encryption-configuration '{
        "Rules": [{
            "ApplyServerSideEncryptionByDefault": {
                "SSEAlgorithm": "AES256"
            }
        }]
    }'

# Block public access
log "Blocking public access..."
aws s3api put-public-access-block \
    --bucket "$BUCKET_NAME" \
    --public-access-block-configuration \
        BlockPublicAcls=true,\
        IgnorePublicAcls=true,\
        BlockPublicPolicy=true,\
        RestrictPublicBuckets=true

# Enable lifecycle policy (optional)
log "Setting up lifecycle policy..."
cat > /tmp/lifecycle.json << 'EOF'
{
    "Rules": [{
        "Id": "DeleteOldVersions",
        "Status": "Enabled",
        "NoncurrentVersionExpiration": {
            "NoncurrentDays": 90
        }
    }]
}
EOF

aws s3api put-bucket-lifecycle-configuration \
    --bucket "$BUCKET_NAME" \
    --lifecycle-configuration file:///tmp/lifecycle.json

# ============================================
# CREATE DYNAMODB TABLE
# ============================================

log "Creating DynamoDB table for state locking..."

aws dynamodb create-table \
    --table-name "$DYNAMODB_TABLE" \
    --attribute-definitions AttributeName=LockID,AttributeType=S \
    --key-schema AttributeName=LockID,KeyType=HASH \
    --provisioned-throughput ReadCapacityUnits=5,WriteCapacityUnits=5 \
    --region "$REGION" \
    2>/dev/null || log "Table already exists"

# ============================================
# VERIFY SETUP
# ============================================

log "Verifying setup..."

# Check S3 bucket
if aws s3 ls "s3://$BUCKET_NAME" &>/dev/null; then
    log "✓ S3 bucket accessible"
else
    log "✗ S3 bucket not accessible"
    exit 1
fi

# Check DynamoDB table
if aws dynamodb describe-table --table-name "$DYNAMODB_TABLE" --region "$REGION" &>/dev/null; then
    log "✓ DynamoDB table exists"
else
    log "✗ DynamoDB table not found"
    exit 1
fi

log "✅ Terraform state backend setup complete!"

cat << EOF

Backend Configuration:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

S3 Bucket:      $BUCKET_NAME
DynamoDB Table: $DYNAMODB_TABLE
Region:         $REGION

Add this to your terraform configuration:

terraform {
  backend "s3" {
    bucket         = "$BUCKET_NAME"
    key            = "path/to/terraform.tfstate"
    region         = "$REGION"
    encrypt        = true
    dynamodb_table = "$DYNAMODB_TABLE"
  }
}

EOF
5.3 State Management Operations
bash#!/bin/bash
# scripts/manage_terraform_state.sh

# ============================================
# TERRAFORM STATE MANAGEMENT OPERATIONS
# ============================================
#
# Common state management operations:
# - List resources
# - Show resource details
# - Move resources
# - Remove resources
# - Import existing resources
# - Pull/push state
#
# ============================================

set -euo pipefail

ENVIRONMENT=${1:-""}
ACTION=${2:-""}

if [ -z "$ENVIRONMENT" ] || [ -z "$ACTION" ]; then
    cat << EOF
Usage: $0 <environment> <action>

Environments: dev, staging, production

Actions:
  list              - List all resources in state
  show <resource>   - Show details of a resource
  mv <src> <dst>    - Move resource in state
  rm <resource>     - Remove resource from state
  import <addr> <id> - Import existing resource
  pull              - Download current state
  push              - Upload local state
  lock              - Manually lock state
  unlock <lock-id>  - Unlock state

Examples:
  $0 production list
  $0 production show module.gpu_server
  $0 production mv module.old module.new
  $0 production rm module.test
EOF
    exit 1
fi

ENV_DIR="terraform/environments/$ENVIRONMENT"

if [ ! -d "$ENV_DIR" ]; then
    echo "ERROR: Environment not found: $ENVIRONMENT"
    exit 1
fi

cd "$ENV_DIR"

case "$ACTION" in
    list)
        echo "Resources in $ENVIRONMENT state:"
        terraform state list
        ;;
    
    show)
        RESOURCE=$3
        if [ -z "$RESOURCE" ]; then
            echo "ERROR: Resource name required"
            exit 1
        fi
        terraform state show "$RESOURCE"
        ;;
    
    mv)
        SRC=$3
        DST=$4
        if [ -z "$SRC" ] || [ -z "$DST" ]; then
            echo "ERROR: Source and destination required"
            exit 1
        fi
        echo "Moving $SRC to $DST"
        terraform state mv "$SRC" "$DST"
        ;;
    
    rm)
        RESOURCE=$3
        if [ -z "$RESOURCE" ]; then
            echo "ERROR: Resource name required"
            exit 1
        fi
        
        read -p "⚠️  Remove $RESOURCE from state? (yes/no): " CONFIRM
        if [ "$CONFIRM" == "yes" ]; then
            terraform state rm "$RESOURCE"
        fi
        ;;
    
    import)
        ADDRESS=$3
        ID=$4
        if [ -z "$ADDRESS" ] || [ -z "$ID" ]; then
            echo "ERROR: Address and ID required"
            exit 1
        fi
        terraform import "$ADDRESS" "$ID"
        ;;
    
    pull)
        echo "Pulling current state..."
        terraform state pull > "terraform.tfstate.backup.$(date +%Y%m%d_%H%M%S)"
        echo "State saved to backup file"
        ;;
    
    push)
        read -p "⚠️  Push local state to remote? (yes/no): " CONFIRM
        if [ "$CONFIRM" == "yes" ]; then
            terraform state push terraform.tfstate
        fi
        ;;
    
    lock)
        echo "Manually locking state..."
        terraform force-unlock -force
        ;;
    
    unlock)
        LOCK_ID=$3
        if [ -z "$LOCK_ID" ]; then
            echo "ERROR: Lock ID required"
            exit 1
        fi
        terraform force-unlock "$LOCK_ID"
        ;;
    
    *)
        echo "ERROR: Unknown action: $ACTION"
        exit 1
        ;;
esac
5.4 State Backup & Recovery
bash#!/bin/bash
# scripts/backup_terraform_state.sh

# ============================================
# TERRAFORM STATE BACKUP & RECOVERY
# ============================================

set -euo pipefail

BACKUP_DIR="backups/terraform_state"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

log() {
    echo "[$(date '+%H:%M:%S')] $*"
}

# ============================================
# BACKUP ALL ENVIRONMENTS
# ============================================

backup_environment() {
    local env=$1
    local env_dir="terraform/environments/$env"
    
    if [ ! -d "$env_dir" ]; then
        log "Skipping $env (not found)"
        return
    fi
    
    log "Backing up $env state..."
    
    cd "$env_dir"
    
    # Pull current state
    terraform state pull > "$BACKUP_DIR/${env}_${TIMESTAMP}.tfstate"
    
    # Compress
    gzip "$BACKUP_DIR/${env}_${TIMESTAMP}.tfstate"
    
    log "✓ Backed up $env to: ${env}_${TIMESTAMP}.tfstate.gz"
    
    cd - > /dev/null
}

log "Starting Terraform state backup..."

backup_environment "dev"
backup_environment "staging"
backup_environment "production"

# ============================================
# CLEANUP OLD BACKUPS
# ============================================

log "Cleaning up old backups (keep last 30)..."
find "$BACKUP_DIR" -name "*.tfstate.gz" -mtime +30 -delete

# ============================================
# UPLOAD TO S3 (Optional)
# ============================================

if command -v aws &> /dev/null; then
    log "Uploading backups to S3..."
    aws s3 sync "$BACKUP_DIR" s3://ocr-terraform-backups/state/ \
        --exclude "*" \
        --include "*_${TIMESTAMP}.tfstate.gz"
fi

log "✅ Backup complete!"

6. 🌍 MULTI-ENVIRONMENT SETUP
6.1 Environment Configuration Matrix
yaml# config/environments.yml

# ============================================
# MULTI-ENVIRONMENT CONFIGURATION
# ============================================

environments:
  
  development:
    name: "Development"
    purpose: "Local development and testing"
    
    infrastructure:
      location: "Local workstation"
      provider: "Docker Compose"
      
      gpu_server:
        enabled: true
        location: "Lenovo Legion T7"
        gpu: "RTX 4080 (16GB)"
        backends:
          - "DeepSeek-Janus-Pro"
          - "GOT-OCR 2.0"
      
      cpu_server:
        enabled: false
        note: "Use CPU backend in Docker"
      
      database:
        type: "PostgreSQL in Docker"
        persistence: "Local volume"
    
    configuration:
      debug_mode: true
      log_level: "DEBUG"
      performance_monitoring: false
      backups: false
      ssl: false
    
    access:
      api_url: "http://localhost:8000"
      database_url: "postgresql://localhost:5432/ocr_dev"
  
  staging:
    name: "Staging"
    purpose: "Pre-production testing"
    
    infrastructure:
      location: "Company datacenter"
      provider: "Proxmox VMs"
      
      gpu_server:
        enabled: true
        specs:
          cores: 12
          memory_gb: 48
          gpu: "RTX 3080 (10GB)"
      
      cpu_server:
        enabled: true
        specs:
          cores: 16
          memory_gb: 32
      
      database:
        type: "PostgreSQL VM"
        specs:
          cores: 4
          memory_gb: 16
          disk_gb: 100
    
    configuration:
      debug_mode: false
      log_level: "INFO"
      performance_monitoring: true
      backups: true
      backup_frequency: "daily"
      ssl: true
      ssl_provider: "Let's Encrypt Staging"
    
    access:
      api_url: "https://staging-api.company.local"
      database_url: "postgresql://staging-db.company.local:5432/ocr_staging"
  
  production:
    name: "Production"
    purpose: "Live production system"
    
    infrastructure:
      location: "Company datacenter"
      provider: "Proxmox VMs"
      
      gpu_server:
        enabled: true
        specs:
          cores: 16
          memory_gb: 64
          gpu: "RTX 4080 (16GB)"
        redundancy: "Single (planned: HA pair)"
      
      cpu_server:
        enabled: true
        specs:
          cores: 32
          memory_gb: 64
        redundancy: "Single (planned: HA pair)"
      
      database:
        type: "PostgreSQL VM"
        specs:
          cores: 8
          memory_gb: 32
          disk_gb: 200
        high_availability: true
        replication: "Streaming replication"
        backup_strategy: "pg_basebackup + WAL archiving"
      
      storage:
        type: "NFS"
        capacity_gb: 2000
    
    configuration:
      debug_mode: false
      log_level: "WARNING"
      performance_monitoring: true
      backups: true
      backup_frequency: "hourly"
      backup_retention:
        daily: 7
        weekly: 4
        monthly: 12
      ssl: true
      ssl_provider: "Let's Encrypt Production"
      rate_limiting: true
      monitoring:
        - prometheus
        - grafana
        - alertmanager
    
    access:
      api_url: "https://api.company.com"
      database_url: "postgresql://prod-db.company.local:5432/ocr_production"
    
    compliance:
      gdpr: true
      audit_logging: true
      data_encryption_at_rest: true
      data_encryption_in_transit: true

# ============================================
# PROMOTION WORKFLOW
# ============================================

promotion_workflow:
  dev_to_staging:
    triggers:
      - "Feature branch merged to develop"
      - "Manual promotion"
    
    steps:
      - "Run integration tests in dev"
      - "Create staging branch"
      - "Deploy to staging"
      - "Run smoke tests"
      - "Notify QA team"
    
    approval: "Not required"
  
  staging_to_production:
    triggers:
      - "Staging tests passed"
      - "Manual promotion only"
    
    steps:
      - "Run full test suite in staging"
      - "Performance benchmarks"
      - "Security scan"
      - "Create production release tag"
      - "Backup production database"
      - "Blue-green deployment"
      - "Health checks"
      - "Rollback plan ready"
    
    approval: "Required from: Tech Lead + Product Manager"
    
    rollback_plan:
      - "Keep previous version running"
      - "Quick DNS/load balancer switch"
      - "Database restore if needed"
6.2 Environment Switcher Script
bash#!/bin/bash
# scripts/switch_environment.sh

# ============================================
# ENVIRONMENT SWITCHER
# ============================================
#
# Easily switch between dev, staging, production
# configurations
#
# ============================================

set -euo pipefail

ENVIRONMENT=${1:-""}

if [ -z "$ENVIRONMENT" ]; then
    echo "Usage: $0 <environment>"
    echo ""
    echo "Available environments:"
    echo "  dev        - Local development"
    echo "  staging    - Pre-production"
    echo "  production - Live production"
    exit 1
fi

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() {
    echo -e "${GREEN}[SWITCH]${NC} $*"
}

warn() {
    echo -e "${YELLOW}[WARNING]${NC} $*"
}

# ============================================
# LOAD ENVIRONMENT CONFIG
# ============================================

load_config() {
    local env=$1
    local config_file="config/environments/${env}.env"
    
    if [ ! -f "$config_file" ]; then
        echo -e "${RED}Error: Config file not found: $config_file${NC}"
        exit 1
    fi
    
    # Backup current .env
    if [ -f ".env" ]; then
        cp .env ".env.backup.$(date +%Y%m%d_%H%M%S)"
    fi
    
    # Load new config
    cp "$config_file" .env
    
    log "Loaded configuration: $config_file"
}

# ============================================
# UPDATE TERRAFORM
# ============================================

update_terraform() {
    local env=$1
    
    if [ -f "terraform/current_env" ]; then
        rm terraform/current_env
    fi
    
    ln -s "environments/$env" terraform/current_env
    
    log "Terraform symlink updated → environments/$env"
}

# ============================================
# UPDATE ANSIBLE
# ============================================

update_ansible() {
    local env=$1
    
    if [ -f "ansible/inventory/current" ]; then
        rm ansible/inventory/current
    fi
    
    ln -s "$env" ansible/inventory/current
    
    log "Ansible inventory updated → $env"
}

# ============================================
# UPDATE DOCKER COMPOSE
# ============================================

update_docker_compose() {
    local env=$1
    local compose_file="docker-compose.${env}.yml"
    
    if [ ! -f "$compose_file" ]; then
        warn "Docker Compose file not found: $compose_file"
        return
    fi
    
    if [ -f "docker-compose.yml" ]; then
        rm docker-compose.yml
    fi
    
    ln -s "$compose_file" docker-compose.yml
    
    log "Docker Compose updated → $compose_file"
}

# ============================================
# DISPLAY ENVIRONMENT INFO
# ============================================

display_info() {
    local env=$1
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  ENVIRONMENT: ${env^^}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # Load and display key settings
    source .env
    
    echo "  API URL:      $API_URL"
    echo "  Database:     $DATABASE_URL"
    echo "  Log Level:    $LOG_LEVEL"
    echo "  Debug Mode:   $DEBUG_MODE"
    echo ""
    
    if [ "$env" == "production" ]; then
        warn "⚠️  You are now targeting PRODUCTION!"
        warn "Be careful with any operations!"
    fi
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# ============================================
# VALIDATION
# ============================================

if [ "$ENVIRONMENT" != "dev" ] && [ "$ENVIRONMENT" != "staging" ] && [ "$ENVIRONMENT" != "production" ]; then
    echo -e "${RED}Error: Invalid environment: $ENVIRONMENT${NC}"
    exit 1
fi

# Confirmation for production
if [ "$ENVIRONMENT" == "production" ]; then
    warn "⚠️  You are about to switch to PRODUCTION!"
    read -p "Are you sure? (yes/no): " CONFIRM
    if [ "$CONFIRM" != "yes" ]; then
        echo "Cancelled"
        exit 0
    fi
fi

# ============================================
# EXECUTE SWITCH
# ============================================

log "Switching to: $ENVIRONMENT"

load_config "$ENVIRONMENT"
update_terraform "$ENVIRONMENT"
update_ansible "$ENVIRONMENT"
update_docker_compose "$ENVIRONMENT"

# Save current environment
echo "$ENVIRONMENT" > .current_env

display_info "$ENVIRONMENT"

log "✅ Environment switched successfully!"
6.3 Environment-Specific Variables
bash# config/environments/dev.env

# ============================================
# DEVELOPMENT ENVIRONMENT
# ============================================

ENVIRONMENT=development

# API
API_URL=http://localhost:8000
API_HOST=0.0.0.0
API_PORT=8000

# Database
DATABASE_URL=postgresql://ocr_user:dev_password@localhost:5432/ocr_dev
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10

# Redis
REDIS_URL=redis://localhost:6379/0

# Backends
BACKEND_A_URL=http://localhost:8001  # DeepSeek
BACKEND_B_URL=http://localhost:8002  # GOT-OCR
BACKEND_C_URL=http://localhost:8003  # Surya

# Logging
LOG_LEVEL=DEBUG
LOG_FORMAT=colored
DEBUG_MODE=true

# Security
SECRET_KEY=dev-secret-key-change-in-production
JWT_ALGORITHM=HS256
JWT_EXPIRY_HOURS=24
CORS_ORIGINS=["http://localhost:3000"]

# Storage
UPLOAD_DIR=./uploads
MAX_UPLOAD_SIZE_MB=50

# Performance
WORKER_PROCESSES=1
WORKER_THREADS=4
REQUEST_TIMEOUT=300

# Features
ENABLE_PROFILING=true
ENABLE_METRICS=false
ENABLE_BACKUPS=false
bash# config/environments/production.env

# ============================================
# PRODUCTION ENVIRONMENT
# ============================================

ENVIRONMENT=production

# API
API_URL=https://api.company.com
API_HOST=0.0.0.0
API_PORT=8000

# Database
DATABASE_URL=postgresql://ocr_user:${POSTGRES_PASSWORD}@10.0.0.30:5432/ocr_production
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=40

# Redis
REDIS_URL=redis://10.0.0.40:6379/0

# Backends
BACKEND_A_URL=http://10.0.0.10:8001
BACKEND_B_URL=http://10.0.0.10:8002
BACKEND_C_URL=http://10.0.0.20:8003

# Logging
LOG_LEVEL=WARNING
LOG_FORMAT=json
DEBUG_MODE=false
SENTRY_DSN=${SENTRY_DSN}

# Security
SECRET_KEY=${SECRET_KEY}
JWT_ALGORITHM=HS256
JWT_EXPIRY_HOURS=8
CORS_ORIGINS=["https://app.company.com"]
RATE_LIMIT_PER_MINUTE=60

# Storage
UPLOAD_DIR=/var/app/uploads
MAX_UPLOAD_SIZE_MB=100
S3_BUCKET=ocr-production-uploads

# Performance
WORKER_PROCESSES=4
WORKER_THREADS=8
REQUEST_TIMEOUT=120

# Features
ENABLE_PROFILING=false
ENABLE_METRICS=true
ENABLE_BACKUPS=true
BACKUP_SCHEDULE="0 */4 * * *"  # Every 4 hours

# Monitoring
PROMETHEUS_PORT=9090
GRAFANA_URL=https://grafana.company.com


INFRASTRUCTURE AS CODE (IaC) GUIDE - TEIL 3

7. 🐳 DOCKER INFRASTRUCTURE
7.1 Docker Compose - GPU Server
yaml# docker-compose.gpu.yml

version: '3.8'

# ============================================
# GPU SERVER - BACKENDS A & B
# ============================================
#
# This compose file runs on the GPU server
# and provides:
# - Backend A: DeepSeek-Janus-Pro
# - Backend B: GOT-OCR 2.0
# - Redis (shared cache)
# - Nginx (reverse proxy)
#
# ============================================

services:
  
  # ==========================================
  # BACKEND A: DeepSeek-Janus-Pro
  # ==========================================
  
  backend-a-deepseek:
    image: ocr-backend-deepseek:latest
    container_name: ocr-backend-a
    
    build:
      context: ./backends/deepseek
      dockerfile: Dockerfile
      args:
        CUDA_VERSION: "12.1"
    
    restart: unless-stopped
    
    ports:
      - "8001:8000"
    
    environment:
      - MODEL_NAME=deepseek-ai/Janus-Pro-7B
      - DEVICE=cuda
      - MAX_BATCH_SIZE=4
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - REDIS_URL=redis://redis:6379/0
    
    volumes:
      - model-cache-deepseek:/root/.cache/huggingface
      - ./logs/backend-a:/var/log/app
    
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
        limits:
          memory: 24G
    
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    
    logging:
      driver: "json-file"
      options:
        max-size: "100m"
        max-file: "5"
    
    networks:
      - ocr-network
  
  # ==========================================
  # BACKEND B: GOT-OCR 2.0
  # ==========================================
  
  backend-b-gotocr:
    image: ocr-backend-gotocr:latest
    container_name: ocr-backend-b
    
    build:
      context: ./backends/gotocr
      dockerfile: Dockerfile
      args:
        CUDA_VERSION: "12.1"
    
    restart: unless-stopped
    
    ports:
      - "8002:8000"
    
    environment:
      - MODEL_NAME=ucaslcl/GOT-OCR2_0
      - DEVICE=cuda
      - MAX_BATCH_SIZE=8
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - REDIS_URL=redis://redis:6379/0
    
    volumes:
      - model-cache-gotocr:/root/.cache/huggingface
      - ./logs/backend-b:/var/log/app
    
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
        limits:
          memory: 16G
    
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    
    logging:
      driver: "json-file"
      options:
        max-size: "100m"
        max-file: "5"
    
    networks:
      - ocr-network
  
  # ==========================================
  # REDIS CACHE
  # ==========================================
  
  redis:
    image: redis:7-alpine
    container_name: ocr-redis
    
    restart: unless-stopped
    
    ports:
      - "6379:6379"
    
    volumes:
      - redis-data:/data
    
    command: >
      redis-server
      --appendonly yes
      --maxmemory 4gb
      --maxmemory-policy allkeys-lru
    
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 3
    
    networks:
      - ocr-network
  
  # ==========================================
  # NGINX REVERSE PROXY
  # ==========================================
  
  nginx:
    image: nginx:alpine
    container_name: ocr-nginx
    
    restart: unless-stopped
    
    ports:
      - "80:80"
      - "443:443"
    
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/conf.d:/etc/nginx/conf.d:ro
      - ./nginx/ssl:/etc/nginx/ssl:ro
      - ./logs/nginx:/var/log/nginx
    
    depends_on:
      - backend-a-deepseek
      - backend-b-gotocr
    
    healthcheck:
      test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    
    networks:
      - ocr-network
  
  # ==========================================
  # MONITORING - PROMETHEUS
  # ==========================================
  
  prometheus:
    image: prom/prometheus:latest
    container_name: ocr-prometheus
    
    restart: unless-stopped
    
    ports:
      - "9090:9090"
    
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus-data:/prometheus
    
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--storage.tsdb.retention.time=30d'
    
    networks:
      - ocr-network
  
  # ==========================================
  # MONITORING - GRAFANA
  # ==========================================
  
  grafana:
    image: grafana/grafana:latest
    container_name: ocr-grafana
    
    restart: unless-stopped
    
    ports:
      - "3000:3000"
    
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD:-admin}
      - GF_USERS_ALLOW_SIGN_UP=false
    
    volumes:
      - grafana-data:/var/lib/grafana
      - ./monitoring/grafana/dashboards:/etc/grafana/provisioning/dashboards:ro
      - ./monitoring/grafana/datasources:/etc/grafana/provisioning/datasources:ro
    
    depends_on:
      - prometheus
    
    networks:
      - ocr-network
  
  # ==========================================
  # GPU METRICS EXPORTER
  # ==========================================
  
  nvidia-exporter:
    image: utkuozdemir/nvidia_gpu_exporter:latest
    container_name: nvidia-exporter
    
    restart: unless-stopped
    
    ports:
      - "9835:9835"
    
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    
    networks:
      - ocr-network

# ============================================
# VOLUMES
# ============================================

volumes:
  model-cache-deepseek:
    driver: local
  model-cache-gotocr:
    driver: local
  redis-data:
    driver: local
  prometheus-data:
    driver: local
  grafana-data:
    driver: local

# ============================================
# NETWORKS
# ============================================

networks:
  ocr-network:
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/16
7.2 Docker Compose - CPU Server
yaml# docker-compose.cpu.yml

version: '3.8'

# ============================================
# CPU SERVER - BACKEND C (SURYA + DOCLING)
# ============================================

services:
  
  # ==========================================
  # BACKEND C: Surya + Docling
  # ==========================================
  
  backend-c-surya:
    image: ocr-backend-surya:latest
    container_name: ocr-backend-c
    
    build:
      context: ./backends/surya
      dockerfile: Dockerfile
    
    restart: unless-stopped
    
    ports:
      - "8003:8000"
    
    environment:
      - MODEL_NAME=vikp/surya_rec2
      - DEVICE=cpu
      - MAX_WORKERS=16
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - REDIS_URL=redis://${REDIS_HOST}:6379/0
    
    volumes:
      - model-cache-surya:/root/.cache/huggingface
      - ./logs/backend-c:/var/log/app
      - /var/app/uploads:/app/uploads:ro
    
    deploy:
      resources:
        limits:
          cpus: '16'
          memory: 32G
    
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    
    logging:
      driver: "json-file"
      options:
        max-size: "100m"
        max-file: "5"
    
    networks:
      - ocr-network

volumes:
  model-cache-surya:
    driver: local

networks:
  ocr-network:
    driver: bridge
7.3 Dockerfile - Backend A (DeepSeek)
dockerfile# backends/deepseek/Dockerfile

# ============================================
# BACKEND A: DeepSeek-Janus-Pro
# ============================================

FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

# Build arguments
ARG CUDA_VERSION=12.1
ARG PYTHON_VERSION=3.11

# Environment
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV CUDA_HOME=/usr/local/cuda
ENV PATH=${CUDA_HOME}/bin:${PATH}
ENV LD_LIBRARY_PATH=${CUDA_HOME}/lib64:${LD_LIBRARY_PATH}

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python${PYTHON_VERSION} \
    python3-pip \
    git \
    wget \
    curl \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip3 install --no-cache-dir -r requirements.txt

# Install PyTorch with CUDA support
RUN pip3 install --no-cache-dir \
    torch torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/cu121

# Copy application code
COPY . .

# Create directories
RUN mkdir -p /var/log/app /tmp/uploads

# Expose port
EXPOSE 8000

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
7.4 Nginx Configuration
nginx# nginx/nginx.conf

# ============================================
# NGINX REVERSE PROXY FOR OCR BACKENDS
# ============================================

user nginx;
worker_processes auto;
error_log /var/log/nginx/error.log warn;
pid /var/run/nginx.pid;

events {
    worker_connections 1024;
    use epoll;
    multi_accept on;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    
    # Logging
    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for" '
                    'rt=$request_time uct="$upstream_connect_time" '
                    'uht="$upstream_header_time" urt="$upstream_response_time"';
    
    access_log /var/log/nginx/access.log main;
    
    # Performance
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;
    
    # Upload limits
    client_max_body_size 100M;
    client_body_buffer_size 128k;
    
    # Gzip
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types text/plain text/css text/xml text/javascript
               application/json application/javascript application/xml+rss
               application/rss+xml font/truetype font/opentype
               application/vnd.ms-fontobject image/svg+xml;
    
    # Upstream backends
    upstream backend_a {
        server backend-a-deepseek:8000 max_fails=3 fail_timeout=30s;
        keepalive 32;
    }
    
    upstream backend_b {
        server backend-b-gotocr:8000 max_fails=3 fail_timeout=30s;
        keepalive 32;
    }
    
    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=60r/m;
    limit_req_status 429;
    
    # Server configuration
    server {
        listen 80;
        server_name _;
        
        # Health check endpoint
        location /health {
            access_log off;
            return 200 "healthy\n";
            add_header Content-Type text/plain;
        }
        
        # Backend A routing
        location /api/v1/deepseek {
            limit_req zone=api_limit burst=10 nodelay;
            
            rewrite ^/api/v1/deepseek/(.*) /$1 break;
            
            proxy_pass http://backend_a;
            proxy_http_version 1.1;
            
            # Headers
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header Connection "";
            
            # Timeouts
            proxy_connect_timeout 60s;
            proxy_send_timeout 300s;
            proxy_read_timeout 300s;
            
            # Buffering
            proxy_buffering on;
            proxy_buffer_size 4k;
            proxy_buffers 8 4k;
            proxy_busy_buffers_size 8k;
        }
        
        # Backend B routing
        location /api/v1/gotocr {
            limit_req zone=api_limit burst=10 nodelay;
            
            rewrite ^/api/v1/gotocr/(.*) /$1 break;
            
            proxy_pass http://backend_b;
            proxy_http_version 1.1;
            
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header Connection "";
            
            proxy_connect_timeout 60s;
            proxy_send_timeout 120s;
            proxy_read_timeout 120s;
            
            proxy_buffering on;
            proxy_buffer_size 4k;
            proxy_buffers 8 4k;
        }
        
        # Metrics endpoint (Prometheus)
        location /metrics {
            stub_status on;
            access_log off;
            allow 172.20.0.0/16;  # Docker network
            deny all;
        }
    }
}
7.5 Docker Management Scripts
bash#!/bin/bash
# scripts/docker_manage.sh

# ============================================
# DOCKER INFRASTRUCTURE MANAGEMENT
# ============================================

set -euo pipefail

ACTION=${1:-""}
SERVICE=${2:-"all"}

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() {
    echo -e "${GREEN}[DOCKER]${NC} $*"
}

error() {
    echo -e "${RED}[ERROR]${NC} $*"
    exit 1
}

# ============================================
# FUNCTIONS
# ============================================

start_services() {
    log "Starting services: $SERVICE"
    
    if [ "$SERVICE" == "all" ]; then
        docker-compose up -d
    else
        docker-compose up -d "$SERVICE"
    fi
    
    log "Services started"
    docker-compose ps
}

stop_services() {
    log "Stopping services: $SERVICE"
    
    if [ "$SERVICE" == "all" ]; then
        docker-compose down
    else
        docker-compose stop "$SERVICE"
    fi
    
    log "Services stopped"
}

restart_services() {
    log "Restarting services: $SERVICE"
    
    if [ "$SERVICE" == "all" ]; then
        docker-compose restart
    else
        docker-compose restart "$SERVICE"
    fi
    
    log "Services restarted"
}

show_logs() {
    log "Showing logs for: $SERVICE"
    
    if [ "$SERVICE" == "all" ]; then
        docker-compose logs -f --tail=100
    else
        docker-compose logs -f --tail=100 "$SERVICE"
    fi
}

show_status() {
    log "Service status:"
    docker-compose ps
    
    echo ""
    log "Resource usage:"
    docker stats --no-stream
}

rebuild_service() {
    log "Rebuilding service: $SERVICE"
    
    if [ "$SERVICE" == "all" ]; then
        docker-compose build --no-cache
    else
        docker-compose build --no-cache "$SERVICE"
    fi
    
    log "Rebuild complete"
}

cleanup() {
    log "Cleaning up Docker resources..."
    
    # Stop all containers
    docker-compose down
    
    # Remove unused images
    docker image prune -af
    
    # Remove unused volumes (careful!)
    read -p "Remove unused volumes? (yes/no): " CONFIRM
    if [ "$CONFIRM" == "yes" ]; then
        docker volume prune -f
    fi
    
    # Remove unused networks
    docker network prune -f
    
    log "Cleanup complete"
}

backup_volumes() {
    log "Backing up Docker volumes..."
    
    BACKUP_DIR="backups/docker_volumes"
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    
    mkdir -p "$BACKUP_DIR"
    
    # Get all volumes
    VOLUMES=$(docker volume ls -q | grep ocr)
    
    for volume in $VOLUMES; do
        log "Backing up volume: $volume"
        
        docker run --rm \
            -v "$volume":/data \
            -v "$(pwd)/$BACKUP_DIR":/backup \
            alpine \
            tar czf "/backup/${volume}_${TIMESTAMP}.tar.gz" -C /data .
        
        log "✓ Backed up: ${volume}_${TIMESTAMP}.tar.gz"
    done
    
    log "All volumes backed up to: $BACKUP_DIR"
}

health_check() {
    log "Running health checks..."
    
    # Check each service
    SERVICES=$(docker-compose ps --services)
    
    for service in $SERVICES; do
        HEALTH=$(docker inspect --format='{{.State.Health.Status}}' "ocr-${service}" 2>/dev/null || echo "unknown")
        
        if [ "$HEALTH" == "healthy" ]; then
            echo -e "  ${GREEN}✓${NC} $service: healthy"
        elif [ "$HEALTH" == "starting" ]; then
            echo -e "  ${YELLOW}⟳${NC} $service: starting"
        else
            echo -e "  ${RED}✗${NC} $service: unhealthy"
        fi
    done
}

# ============================================
# MAIN
# ============================================

case "$ACTION" in
    start)
        start_services
        ;;
    stop)
        stop_services
        ;;
    restart)
        restart_services
        ;;
    logs)
        show_logs
        ;;
    status)
        show_status
        ;;
    rebuild)
        rebuild_service
        ;;
    cleanup)
        cleanup
        ;;
    backup)
        backup_volumes
        ;;
    health)
        health_check
        ;;
    *)
        cat << EOF
Usage: $0 <action> [service]

Actions:
  start       - Start services
  stop        - Stop services
  restart     - Restart services
  logs        - Show logs (follow mode)
  status      - Show service status
  rebuild     - Rebuild service images
  cleanup     - Clean up Docker resources
  backup      - Backup Docker volumes
  health      - Run health checks

Services:
  all                    - All services (default)
  backend-a-deepseek     - Backend A
  backend-b-gotocr       - Backend B
  nginx                  - Nginx proxy
  redis                  - Redis cache
  prometheus             - Prometheus
  grafana                - Grafana

Examples:
  $0 start
  $0 restart backend-a-deepseek
  $0 logs nginx
  $0 status
EOF
        exit 1
        ;;
esac

8. 💻 GPU SERVER CONFIGURATION
8.1 NVIDIA Driver Installation
yaml# ansible/roles/nvidia_drivers/tasks/main.yml

---
- name: Install NVIDIA Drivers and CUDA
  
  # ==========================================
  # PRE-INSTALLATION CHECKS
  # ==========================================
  
  - name: Check if NVIDIA GPU is present
    shell: lspci | grep -i nvidia
    register: nvidia_check
    failed_when: false
    changed_when: false
  
  - name: Fail if no NVIDIA GPU found
    fail:
      msg: "No NVIDIA GPU detected on this system"
    when: nvidia_check.rc != 0
  
  - name: Display detected NVIDIA GPU
    debug:
      msg: "{{ nvidia_check.stdout_lines }}"
  
  # ==========================================
  # SYSTEM PREPARATION
  # ==========================================
  
  - name: Update package cache
    apt:
      update_cache: yes
      cache_valid_time: 3600
  
  - name: Install prerequisites
    apt:
      name:
        - build-essential
        - dkms
        - linux-headers-{{ ansible_kernel }}
      state: present
  
  - name: Remove nouveau driver
    block:
      - name: Blacklist nouveau
        copy:
          dest: /etc/modprobe.d/blacklist-nouveau.conf
          content: |
            blacklist nouveau
            options nouveau modeset=0
      
      - name: Update initramfs
        command: update-initramfs -u
        register: initramfs_update
        changed_when: initramfs_update.rc == 0
  
  # ==========================================
  # NVIDIA DRIVER INSTALLATION
  # ==========================================
  
  - name: Add NVIDIA driver PPA
    apt_repository:
      repo: ppa:graphics-drivers/ppa
      state: present
      update_cache: yes
  
  - name: Install NVIDIA driver
    apt:
      name: "nvidia-driver-{{ nvidia_driver_version }}"
      state: present
    notify: reboot_required
  
  - name: Check if reboot is required
    stat:
      path: /var/run/reboot-required
    register: reboot_required_file
  
  - name: Reboot if required
    reboot:
      reboot_timeout: 600
    when: reboot_required_file.stat.exists
  
  # ==========================================
  # VERIFY DRIVER INSTALLATION
  # ==========================================
  
  - name: Wait for system to come back online
    wait_for_connection:
      delay: 30
      timeout: 300
    when: reboot_required_file.stat.exists
  
  - name: Verify NVIDIA driver
    command: nvidia-smi
    register: nvidia_smi
    changed_when: false
  
  - name: Display nvidia-smi output
    debug:
      msg: "{{ nvidia_smi.stdout_lines }}"
  
  # ==========================================
  # CUDA TOOLKIT INSTALLATION
  # ==========================================
  
  - name: Download CUDA keyring
    get_url:
      url: "https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/cuda-keyring_1.1-1_all.deb"
      dest: /tmp/cuda-keyring.deb
  
  - name: Install CUDA keyring
    apt:
      deb: /tmp/cuda-keyring.deb
  
  - name: Update package cache after adding CUDA repo
    apt:
      update_cache: yes
  
  - name: Install CUDA toolkit
    apt:
      name: "cuda-toolkit-{{ cuda_version | replace('.', '-') }}"
      state: present
  
  # ==========================================
  # ENVIRONMENT CONFIGURATION
  # ==========================================
  
  - name: Configure CUDA environment variables
    blockinfile:
      path: /etc/environment
      block: |
        CUDA_HOME=/usr/local/cuda
        PATH=/usr/local/cuda/bin:$PATH
        LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH
      marker: "# {mark} ANSIBLE MANAGED CUDA ENV"
  
  - name: Configure ld.so.conf for CUDA
    copy:
      dest: /etc/ld.so.conf.d/cuda.conf
      content: |
        /usr/local/cuda/lib64
        /usr/local/cuda/extras/CUPTI/lib64
    notify: run_ldconfig
  
  # ==========================================
  # NVIDIA PERSISTENCE DAEMON
  # ==========================================
  
  - name: Enable NVIDIA persistence mode
    copy:
      dest: /etc/systemd/system/nvidia-persistenced.service
      content: |
        [Unit]
        Description=NVIDIA Persistence Daemon
        Wants=syslog.target
        
        [Service]
        Type=forking
        ExecStart=/usr/bin/nvidia-persistenced --user nvidia-persistenced --verbose
        ExecStopPost=/bin/rm -rf /var/run/nvidia-persistenced
        
        [Install]
        WantedBy=multi-user.target
  
  - name: Start and enable nvidia-persistenced
    systemd:
      name: nvidia-persistenced
      state: started
      enabled: yes
      daemon_reload: yes
  
  # ==========================================
  # GPU SETTINGS OPTIMIZATION
  # ==========================================
  
  - name: Set GPU power limit (if specified)
    command: "nvidia-smi -pl {{ gpu_power_limit }}"
    when: gpu_power_limit is defined
    changed_when: false
  
  - name: Set GPU fan speed (if specified)
    command: "nvidia-smi -i 0 --gpcclkmin={{ gpu_fan_speed }}"
    when: gpu_fan_speed is defined
    changed_when: false
  
  # ==========================================
  # MONITORING SETUP
  # ==========================================
  
  - name: Install nvidia_gpu_exporter
    block:
      - name: Download nvidia_gpu_exporter
        get_url:
          url: "https://github.com/utkuozdemir/nvidia_gpu_exporter/releases/download/v1.2.0/nvidia_gpu_exporter_1.2.0_linux_x86_64.tar.gz"
          dest: /tmp/nvidia_exporter.tar.gz
      
      - name: Extract nvidia_gpu_exporter
        unarchive:
          src: /tmp/nvidia_exporter.tar.gz
          dest: /usr/local/bin/
          remote_src: yes
          mode: '0755'
      
      - name: Create nvidia_exporter systemd service
        copy:
          dest: /etc/systemd/system/nvidia_exporter.service
          content: |
            [Unit]
            Description=NVIDIA GPU Prometheus Exporter
            After=network.target
            
            [Service]
            Type=simple
            User=nobody
            ExecStart=/usr/local/bin/nvidia_gpu_exporter
            Restart=on-failure
            RestartSec=5
            
            [Install]
            WantedBy=multi-user.target
        notify: reload_systemd
      
      - name: Start nvidia_exporter
        systemd:
          name: nvidia_exporter
          state: started
          enabled: yes

# ==========================================
# HANDLERS
# ==========================================

handlers:
  - name: reboot_required
    debug:
      msg: "Reboot is required to load NVIDIA drivers"
  
  - name: run_ldconfig
    command: ldconfig
  
  - name: reload_systemd
    systemd:
      daemon_reload: yes
8.2 GPU Monitoring Configuration
yaml# monitoring/prometheus.yml

# ============================================
# PROMETHEUS CONFIGURATION FOR GPU MONITORING
# ============================================

global:
  scrape_interval: 15s
  evaluation_interval: 15s
  external_labels:
    cluster: 'ocr-production'
    environment: 'production'

# ==========================================
# ALERTING
# ==========================================

alerting:
  alertmanagers:
    - static_configs:
        - targets:
            - alertmanager:9093

# ==========================================
# RULE FILES
# ==========================================

rule_files:
  - 'alerts/gpu_alerts.yml'
  - 'alerts/backend_alerts.yml'

# ==========================================
# SCRAPE CONFIGS
# ==========================================

scrape_configs:
  
  # Prometheus itself
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']
  
  # GPU Server - NVIDIA Metrics
  - job_name: 'nvidia_gpu'
    static_configs:
      - targets: ['gpu-server:9835']
        labels:
          server: 'gpu-prod'
          location: 'datacenter'
  
  # Backend A - DeepSeek
  - job_name: 'backend_a'
    static_configs:
      - targets: ['backend-a-deepseek:8000']
        labels:
          backend: 'deepseek'
          tier: 'gpu'
  
  # Backend B - GOT-OCR
  - job_name: 'backend_b'
    static_configs:
      - targets: ['backend-b-gotocr:8000']
        labels:
          backend: 'gotocr'
          tier: 'gpu'
  
  # Backend C - Surya (CPU)
  - job_name: 'backend_c'
    static_configs:
      - targets: ['cpu-server:8003']
        labels:
          backend: 'surya'
          tier: 'cpu'
  
  # PostgreSQL
  - job_name: 'postgresql'
    static_configs:
      - targets: ['db-server:9187']
        labels:
          service: 'postgresql'
  
  # Redis
  - job_name: 'redis'
    static_configs:
      - targets: ['redis:9121']
        labels:
          service: 'redis'
  
  # Node Exporter (System Metrics)
  - job_name: 'node'
    static_configs:
      - targets:
          - 'gpu-server:9100'
          - 'cpu-server:9100'
          - 'db-server:9100'
        labels:
          job: 'node_exporter'
8.3 GPU Alert Rules
yaml# monitoring/alerts/gpu_alerts.yml

# ============================================
# GPU MONITORING ALERT RULES
# ============================================

groups:
  - name: gpu_alerts
    interval: 30s
    rules:
      
      # ==========================================
      # GPU UTILIZATION
      # ==========================================
      
      - alert: GPUHighUtilization
        expr: nvidia_gpu_duty_cycle > 95
        for: 10m
        labels:
          severity: warning
          component: gpu
        annotations:
          summary: "GPU utilization very high"
          description: "GPU {{ $labels.uuid }} utilization is {{ $value }}% for 10 minutes"
      
      - alert: GPULowUtilization
        expr: nvidia_gpu_duty_cycle < 10
        for: 30m
        labels:
          severity: info
          component: gpu
        annotations:
          summary: "GPU underutilized"
          description: "GPU {{ $labels.uuid }} utilization only {{ $value }}% - might be idle"
      
      # ==========================================
      # GPU MEMORY
      # ==========================================
      
      - alert: GPUMemoryHigh
        expr: (nvidia_gpu_memory_used_bytes / nvidia_gpu_memory_total_bytes) > 0.90
        for: 5m
        labels:
          severity: warning
          component: gpu
        annotations:
          summary: "GPU memory usage high"
          description: "GPU {{ $labels.uuid }} memory at {{ $value | humanizePercentage }}"
      
      - alert: GPUMemoryCritical
        expr: (nvidia_gpu_memory_used_bytes / nvidia_gpu_memory_total_bytes) > 0.95
        for: 2m
        labels:
          severity: critical
          component: gpu
        annotations:
          summary: "GPU memory critically high!"
          description: "GPU {{ $labels.uuid }} memory at {{ $value | humanizePercentage }} - risk of OOM!"
      
      # ==========================================
      # GPU TEMPERATURE
      # ==========================================
      
      - alert: GPUTemperatureHigh
        expr: nvidia_gpu_temperature_celsius > 80
        for: 5m
        labels:
          severity: warning
          component: gpu
        annotations:
          summary: "GPU temperature elevated"
          description: "GPU {{ $labels.uuid }} temperature is {{ $value }}°C"
      
      - alert: GPUTemperatureCritical
        expr: nvidia_gpu_temperature_celsius > 90
        for: 1m
        labels:
          severity: critical
          component: gpu
        annotations:
          summary: "GPU temperature critical!"
          description: "GPU {{ $labels.uuid }} temperature is {{ $value }}°C - risk of thermal throttling!"
      
      # ==========================================
      # GPU POWER
      # ==========================================
      
      - alert: GPUPowerLimitReached
        expr: nvidia_gpu_power_usage_milliwatts / 1000 >= nvidia_gpu_power_limit_watts * 0.95
        for: 10m
        labels:
          severity: info
          component: gpu
        annotations:
          summary: "GPU hitting power limit"
          description: "GPU {{ $labels.uuid }} power usage near limit - may throttle"
      
      # ==========================================
      # GPU ERRORS
      # ==========================================
      
      - alert: GPUXidErrors
        expr: increase(nvidia_gpu_xid_errors_total[5m]) > 0
        labels:
          severity: critical
          component: gpu
        annotations:
          summary: "GPU Xid errors detected"
          description: "GPU {{ $labels.uuid }} reported {{ $value }} Xid errors - hardware issue!"
      
      # ==========================================
      # GPU AVAILABILITY
      # ==========================================
      
      - alert: GPUDown
        expr: up{job="nvidia_gpu"} == 0
        for: 1m
        labels:
          severity: critical
          component: gpu
        annotations:
          summary: "GPU exporter down"
          description: "Cannot scrape GPU metrics from {{ $labels.instance }}"

9. 📊 MONITORING & OBSERVABILITY
9.1 Grafana Dashboard - GPU Metrics
json{
  "dashboard": {
    "title": "OCR System - GPU Monitoring",
    "uid": "ocr-gpu-monitoring",
    "tags": ["ocr", "gpu", "nvidia"],
    "timezone": "browser",
    "panels": [
      {
        "id": 1,
        "title": "GPU Utilization",
        "type": "graph",
        "targets": [
          {
            "expr": "nvidia_gpu_duty_cycle",
            "legendFormat": "GPU {{ uuid }} - {{ name }}"
          }
        ],
        "yaxes": [
          {
            "format": "percent",
            "max": 100,
            "min": 0
          }
        ],
        "alert": {
          "conditions": [
            {
              "evaluator": {
                "params": [95],
                "type": "gt"
              },
              "query": {
                "params": ["A", "5m", "now"]
              }
            }
          ],
          "name": "GPU High Utilization"
        }
      },
      {
        "id": 2,
        "title": "GPU Memory Usage",
        "type": "graph",
        "targets": [
          {
            "expr": "nvidia_gpu_memory_used_bytes / 1024 / 1024 / 1024",
            "legendFormat": "Used - GPU {{ uuid }}"
          },
          {
            "expr": "nvidia_gpu_memory_total_bytes / 1024 / 1024 / 1024",
            "legendFormat": "Total - GPU {{ uuid }}"
          }
        ],
        "yaxes": [
          {
            "format": "decgbytes",
            "min": 0
          }
        ]
      },
      {
        "id": 3,
        "title": "GPU Temperature",
        "type": "graph",
        "targets": [
          {
            "expr": "nvidia_gpu_temperature_celsius",
            "legendFormat": "GPU {{ uuid }}"
          }
        ],
        "yaxes": [
          {
            "format": "celsius",
            "max": 100,
            "min": 0
          }
        ],
        "thresholds": [
          {
            "value": 80,
            "colorMode": "critical",
            "op": "gt"
          },
          {
            "value": 70,
            "colorMode": "warning",
            "op": "gt"
          }
        ]
      },
      {
        "id": 4,
        "title": "GPU Power Usage",
        "type": "graph",
        "targets": [
          {
            "expr": "nvidia_gpu_power_usage_milliwatts / 1000",
            "legendFormat": "Power - GPU {{ uuid }}"
          },
          {
            "expr": "nvidia_gpu_power_limit_watts",
            "legendFormat": "Limit - GPU {{ uuid }}"
          }
        ],
        "yaxes": [
          {
            "format": "watt",
            "min": 0
          }
        ]
      },
      {
        "id": 5,
        "title": "Backend Processing Time",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(backend_processing_time_sum[5m]) / rate(backend_processing_time_count[5m])",
            "legendFormat": "{{ backend }}"
          }
        ],
        "yaxes": [
          {
            "format": "s",
            "min": 0
          }
        ]
      },
      {
        "id": 6,
        "title": "Request Rate",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(backend_requests_total[5m])",
            "legendFormat": "{{ backend }}"
          }
        ],
        "yaxes": [
          {
            "format": "reqps",
            "min": 0
          }
        ]
      }
    ],
    "refresh": "10s"
  }
}
9.2 Application Metrics (FastAPI)
python# backends/common/metrics.py

"""
Prometheus metrics for OCR backends
"""

from prometheus_client import Counter, Histogram, Gauge, Info
import time
from functools import wraps

# ============================================
# DEFINE METRICS
# ============================================

# Request counter
backend_requests_total = Counter(
    'backend_requests_total',
    'Total number of OCR requests',
    ['backend', 'method', 'status']
)

# Processing time histogram
backend_processing_time = Histogram(
    'backend_processing_time_seconds',
    'Time spent processing OCR requests',
    ['backend', 'document_type'],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
)

# Active requests gauge
backend_active_requests = Gauge(
    'backend_active_requests',
    'Number of currently processing requests',
    ['backend']
)

# Model info
backend_model_info = Info(
    'backend_model_info',
    'Information about loaded model',
    ['backend']
)

# GPU metrics
gpu_memory_allocated = Gauge(
    'gpu_memory_allocated_bytes',
    'GPU memory allocated by PyTorch',
    ['backend', 'device']
)

gpu_memory_reserved = Gauge(
    'gpu_memory_reserved_bytes',
    'GPU memory reserved by PyTorch',
    ['backend', 'device']
)

# Error counter
backend_errors_total = Counter(
    'backend_errors_total',
    'Total number of errors',
    ['backend', 'error_type']
)

# Queue size
backend_queue_size = Gauge(
    'backend_queue_size',
    'Number of requests in queue',
    ['backend']
)

# ============================================
# METRIC DECORATORS
# ============================================

def track_processing_time(backend_name: str, document_type: str = "unknown"):
    """Decorator to track processing time"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            backend_active_requests.labels(backend=backend_name).inc()
            
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                
                backend_processing_time.labels(
                    backend=backend_name,
                    document_type=document_type
                ).observe(duration)
                
                backend_requests_total.labels(
                    backend=backend_name,
                    method='ocr',
                    status='success'
                ).inc()
                
                return result
                
            except Exception as e:
                backend_errors_total.labels(
                    backend=backend_name,
                    error_type=type(e).__name__
                ).inc()
                
                backend_requests_total.labels(
                    backend=backend_name,
                    method='ocr',
                    status='error'
                ).inc()
                
                raise
                
            finally:
                backend_active_requests.labels(backend=backend_name).dec()
        
        return wrapper
    return decorator


def update_gpu_metrics(backend_name: str, device: str):
    """Update GPU memory metrics"""
    try:
        import torch
        
        if torch.cuda.is_available():
            allocated = torch.cuda.memory_allocated(device)
            reserved = torch.cuda.memory_reserved(device)
            
            gpu_memory_allocated.labels(
                backend=backend_name,
                device=device
            ).set(allocated)
            
            gpu_memory_reserved.labels(
                backend=backend_name,
                device=device
            ).set(reserved)
    except Exception as e:
        print(f"Error updating GPU metrics: {e}")


# ============================================
# USAGE EXAMPLE
# ============================================

"""
from metrics import track_processing_time, backend_model_info

# Set model info once at startup
backend_model_info.labels(backend='deepseek').info({
    'model_name': 'deepseek-ai/Janus-Pro-7B',
    'version': '1.0',
    'device': 'cuda:0'
})

# Use decorator on processing function
@track_processing_time('deepseek', 'invoice')
async def process_document(image):
    # ... processing logic
    return result
"""


INFRASTRUCTURE AS CODE (IaC) GUIDE - TEIL 4 (FINAL)

10. 📚 BEST PRACTICES & PATTERNS
10.1 IaC Golden Rules
markdown# INFRASTRUCTURE AS CODE - GOLDEN RULES

## ✅ DO's

### 1. Version Control Everything
```bash
# Good: Everything in Git
git/
├── terraform/
├── ansible/
├── docker/
└── scripts/

# Bad: Manual configurations, no version control
```

### 2. Use Modules & Roles
```hcl
# Good: Reusable modules
module "gpu_server" {
  source = "../../modules/gpu_server"
  # ...
}

# Bad: Duplicate code everywhere
resource "proxmox_vm_qemu" "gpu1" { ... }
resource "proxmox_vm_qemu" "gpu2" { ... }
```

### 3. Separate Environments
```
environments/
├── dev/
├── staging/
└── production/

# Never mix environments!
```

### 4. Use Variables & Secrets Management
```hcl
# Good: Variables
variable "db_password" {
  type      = string
  sensitive = true
}

# Bad: Hardcoded secrets
password = "mysecretpassword123"
```

### 5. Implement State Locking
```hcl
# Good: Remote state with locking
backend "s3" {
  dynamodb_table = "terraform-locks"
  encrypt        = true
}

# Bad: Local state, no locking
```

### 6. Test Before Apply
```bash
# Always:
terraform plan
ansible-playbook --check

# Never:
terraform apply -auto-approve  # In production!
```

### 7. Document Everything
```yaml
# Good: Self-documenting code
- name: Install NVIDIA drivers for GPU Backend A (DeepSeek)
  apt:
    name: nvidia-driver-535
    state: present
  tags: [gpu, nvidia, backend-a]

# Bad: No context
- apt: name=nvidia-driver-535
```

### 8. Use Tags & Labels
```hcl
# Good: Organized resources
tags = {
  Project     = "OCR-System"
  Environment = "Production"
  ManagedBy   = "Terraform"
  Backend     = "DeepSeek"
  CostCenter  = "Engineering"
}
```

## ❌ DON'Ts

### 1. Don't Hardcode Values
```hcl
# Bad
ip_address = "10.0.0.42"

# Good
ip_address = var.gpu_server_ip
```

### 2. Don't Store Secrets in Git
```bash
# Bad: Secrets in plain text
git add secrets.env

# Good: Use Ansible Vault or external secrets manager
ansible-vault encrypt secrets.yml
```

### 3. Don't Skip State Backups
```bash
# Bad: No backups
terraform destroy  # Oops!

# Good: Regular backups
./scripts/backup_terraform_state.sh
```

### 4. Don't Mix Manual & IaC Changes
```bash
# Bad: SSH into server and apt install something

# Good: Add to Ansible playbook
- name: Install additional package
  apt:
    name: htop
```

### 5. Don't Ignore Drift Detection
```bash
# Bad: Never check for drift

# Good: Regular drift detection
terraform plan  # Should show "No changes"
```

### 6. Don't Use Root/Admin Everywhere
```yaml
# Bad
become_user: root

# Good
become_user: app_user
```

### 7. Don't Forget Rollback Plans
```bash
# Bad: Deploy without rollback plan

# Good: Always have rollback ready
git tag production-v1.2.3
terraform state pull > backup.tfstate
```

### 8. Don't Neglect Monitoring
```yaml
# Bad: Deploy and forget

# Good: Monitor everything
- prometheus
- grafana
- alertmanager
- logging
```
10.2 Infrastructure Patterns
yaml# infrastructure/patterns.yml

# ============================================
# COMMON INFRASTRUCTURE PATTERNS
# ============================================

patterns:
  
  # ==========================================
  # PATTERN 1: IMMUTABLE INFRASTRUCTURE
  # ==========================================
  
  immutable_infrastructure:
    principle: "Never modify existing servers - replace them"
    
    implementation:
      - "Build new server with updated configuration"
      - "Test new server"
      - "Switch traffic to new server"
      - "Destroy old server"
    
    benefits:
      - "Consistent, reproducible deployments"
      - "Easy rollback"
      - "No configuration drift"
      - "Safer deployments"
    
    example:
      - "Blue-green deployments"
      - "Canary releases"
      - "Container-based deployments"
  
  # ==========================================
  # PATTERN 2: INFRASTRUCTURE AS CODE
  # ==========================================
  
  infrastructure_as_code:
    principle: "Define infrastructure in code, not clicks"
    
    benefits:
      - "Version controlled"
      - "Peer reviewed"
      - "Automated testing"
      - "Documentation"
      - "Disaster recovery"
    
    tools:
      declarative:
        - Terraform
        - CloudFormation
        - Pulumi
      imperative:
        - Ansible
        - Chef
        - Puppet
  
  # ==========================================
  # PATTERN 3: SEPARATION OF CONCERNS
  # ==========================================
  
  separation_of_concerns:
    principle: "Different tools for different layers"
    
    layers:
      infrastructure_provisioning:
        tool: "Terraform"
        responsibility: "Create VMs, networks, storage"
      
      configuration_management:
        tool: "Ansible"
        responsibility: "Install software, configure services"
      
      application_deployment:
        tool: "Docker Compose / Kubernetes"
        responsibility: "Deploy application containers"
      
      monitoring:
        tool: "Prometheus + Grafana"
        responsibility: "Observe system health"
  
  # ==========================================
  # PATTERN 4: ENVIRONMENT PARITY
  # ==========================================
  
  environment_parity:
    principle: "Dev, staging, prod should be as similar as possible"
    
    same_across_environments:
      - "Operating system version"
      - "Software versions"
      - "Configuration structure"
      - "Deployment process"
    
    different_across_environments:
      - "Resource sizes (dev smaller)"
      - "Secrets/credentials"
      - "Backup frequency"
      - "Monitoring sensitivity"
    
    implementation:
      - "Use same Terraform modules"
      - "Parameterize differences"
      - "Test in staging first"
  
  # ==========================================
  # PATTERN 5: GITOPS
  # ==========================================
  
  gitops:
    principle: "Git is the single source of truth"
    
    workflow:
      - "Developer commits infrastructure change to Git"
      - "CI/CD pipeline tests the change"
      - "Peer review via pull request"
      - "Merge triggers automated deployment"
      - "System reconciles to Git state"
    
    benefits:
      - "Audit trail (Git history)"
      - "Easy rollback (Git revert)"
      - "Collaboration (Pull requests)"
      - "Automated deployments"
  
  # ==========================================
  # PATTERN 6: CATTLE NOT PETS
  # ==========================================
  
  cattle_not_pets:
    principle: "Servers are disposable, not precious"
    
    pets_approach:
      - "Named servers (web-server-01)"
      - "Manual updates"
      - "Long-lived"
      - "Carefully maintained"
    
    cattle_approach:
      - "Numbered instances (web-001, web-002)"
      - "Automated deployment"
      - "Disposable"
      - "Replaced, not fixed"
    
    implementation:
      - "Automate server creation"
      - "Configuration in code"
      - "Stateless where possible"
      - "Data in external storage"
10.3 Security Best Practices
yaml# security/best_practices.yml

# ============================================
# SECURITY BEST PRACTICES FOR IaC
# ============================================

security_practices:
  
  # ==========================================
  # SECRETS MANAGEMENT
  # ==========================================
  
  secrets_management:
    
    do:
      - name: "Use Ansible Vault for sensitive data"
        example: |
          ansible-vault encrypt secrets.yml
          ansible-playbook site.yml --ask-vault-pass
      
      - name: "Use environment variables"
        example: |
          DATABASE_PASSWORD=${DB_PASSWORD}
      
      - name: "Use external secrets managers"
        tools:
          - "HashiCorp Vault"
          - "AWS Secrets Manager"
          - "Azure Key Vault"
      
      - name: "Rotate secrets regularly"
        frequency: "Every 90 days minimum"
    
    dont:
      - "Store secrets in Git (even private repos)"
      - "Hardcode passwords in Terraform/Ansible"
      - "Share secrets via email/Slack"
      - "Use same secrets across environments"
  
  # ==========================================
  # ACCESS CONTROL
  # ==========================================
  
  access_control:
    
    ssh_access:
      - "Use SSH keys, not passwords"
      - "Different keys per user"
      - "Disable root login"
      - "Use bastion/jump hosts"
      - "Rotate SSH keys regularly"
    
    example_sshd_config: |
      PermitRootLogin no
      PasswordAuthentication no
      PubkeyAuthentication yes
      AllowUsers deployer ansible
    
    sudo_access:
      - "Principle of least privilege"
      - "Use sudo, not root login"
      - "Audit sudo usage"
      - "Time-limited sudo sessions"
  
  # ==========================================
  # NETWORK SECURITY
  # ==========================================
  
  network_security:
    
    firewall_rules:
      - "Default deny all traffic"
      - "Explicitly allow required ports"
      - "Whitelist specific IPs where possible"
      - "Separate internal/external networks"
    
    example_ufw_rules: |
      # Default policies
      ufw default deny incoming
      ufw default allow outgoing
      
      # SSH (from office only)
      ufw allow from 192.168.1.0/24 to any port 22
      
      # HTTPS (public)
      ufw allow 443/tcp
      
      # Application (internal only)
      ufw allow from 10.0.0.0/24 to any port 8000
    
    ssl_tls:
      - "Use HTTPS everywhere"
      - "Let's Encrypt for certificates"
      - "TLS 1.2+ only"
      - "Strong cipher suites"
  
  # ==========================================
  # INFRASTRUCTURE HARDENING
  # ==========================================
  
  infrastructure_hardening:
    
    os_hardening:
      - "Regular security updates"
      - "Remove unused packages"
      - "Disable unused services"
      - "Configure fail2ban"
      - "Enable SELinux/AppArmor"
    
    docker_security:
      - "Run containers as non-root"
      - "Use official images"
      - "Scan images for vulnerabilities"
      - "Limit container resources"
      - "Use Docker secrets"
    
    database_security:
      - "Strong passwords"
      - "Limit network access"
      - "Encrypt connections (SSL)"
      - "Regular backups"
      - "Audit logging"
  
  # ==========================================
  # MONITORING & AUDITING
  # ==========================================
  
  monitoring_auditing:
    
    logging:
      - "Centralized logging"
      - "Log all authentication attempts"
      - "Log configuration changes"
      - "Retain logs for compliance"
    
    monitoring:
      - "Monitor failed login attempts"
      - "Alert on configuration changes"
      - "Track resource usage"
      - "Monitor network traffic"
    
    auditing:
      - "Regular security audits"
      - "Vulnerability scanning"
      - "Penetration testing"
      - "Compliance checks"

11. 🔧 TROUBLESHOOTING & RECOVERY
11.1 Common Issues & Solutions
bash#!/bin/bash
# scripts/troubleshoot.sh

# ============================================
# INFRASTRUCTURE TROUBLESHOOTING GUIDE
# ============================================

cat << 'EOF'
╔════════════════════════════════════════════════════════════╗
║         INFRASTRUCTURE TROUBLESHOOTING GUIDE               ║
╚════════════════════════════════════════════════════════════╝

TERRAFORM ISSUES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. STATE LOCK ERROR
   Problem: "Error acquiring the state lock"
   
   Cause: Previous terraform run didn't release lock
   
   Solution:
   $ terraform force-unlock <LOCK_ID>
   
   Prevention: Always let terraform finish properly

2. RESOURCE ALREADY EXISTS
   Problem: "Error: resource already exists"
   
   Cause: Resource created outside Terraform
   
   Solution:
   $ terraform import <resource_type>.<name> <id>
   
   Example:
   $ terraform import proxmox_vm_qemu.gpu_server 101

3. STATE OUT OF SYNC
   Problem: "Resources in state don't match reality"
   
   Solution:
   $ terraform refresh
   $ terraform plan
   
   Or manually fix:
   $ terraform state rm <resource>
   $ terraform import <resource> <id>

4. PROVIDER AUTHENTICATION FAILED
   Problem: "Error: authentication failed"
   
   Solution:
   $ export PROXMOX_PASSWORD="your-password"
   $ terraform init -reconfigure

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ANSIBLE ISSUES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. SSH CONNECTION FAILED
   Problem: "Failed to connect to host"
   
   Solutions:
   # Test SSH manually
   $ ssh -vvv ubuntu@10.0.0.10
   
   # Add to known_hosts
   $ ssh-keyscan 10.0.0.10 >> ~/.ssh/known_hosts
   
   # Check Ansible config
   $ ansible all -m ping -i inventory/production/hosts.yml

2. PRIVILEGE ESCALATION FAILED
   Problem: "Failed to become user root"
   
   Solutions:
   # Check sudo access
   $ ssh ubuntu@10.0.0.10 'sudo -l'
   
   # Add to playbook
   become: yes
   become_user: root
   become_method: sudo

3. MODULE NOT FOUND
   Problem: "ERROR! couldn't resolve module/action"
   
   Solutions:
   # Install collection
   $ ansible-galaxy collection install community.general
   
   # Or install requirements
   $ ansible-galaxy install -r requirements.yml

4. VAULT PASSWORD ERROR
   Problem: "ERROR! Vault password required"
   
   Solutions:
   # Provide password file
   $ ansible-playbook --vault-password-file .vault_pass
   
   # Or prompt
   $ ansible-playbook --ask-vault-pass

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DOCKER ISSUES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. CONTAINER WON'T START
   Problem: Container exits immediately
   
   Debug:
   $ docker logs <container_name>
   $ docker inspect <container_name>
   
   Common causes:
   - Missing environment variables
   - Port already in use
   - Volume mount errors
   - Incorrect entrypoint

2. GPU NOT AVAILABLE IN CONTAINER
   Problem: "CUDA not available" inside container
   
   Solutions:
   # Check NVIDIA runtime
   $ docker run --rm --gpus all nvidia/cuda:12.1.0-base nvidia-smi
   
   # Verify Docker daemon config
   $ cat /etc/docker/daemon.json
   {
     "default-runtime": "nvidia",
     "runtimes": {
       "nvidia": {
         "path": "nvidia-container-runtime"
       }
     }
   }
   
   # Restart Docker
   $ sudo systemctl restart docker

3. CONTAINER OUT OF MEMORY
   Problem: Container killed, exit code 137
   
   Solutions:
   # Check memory usage
   $ docker stats
   
   # Increase memory limit
   deploy:
     resources:
       limits:
         memory: 32G

4. IMAGE BUILD FAILS
   Problem: "ERROR: failed to build"
   
   Debug:
   # Build with verbose output
   $ docker build --progress=plain --no-cache .
   
   # Check build context size
   $ docker build --progress=plain . 2>&1 | grep "Sending build context"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

GPU ISSUES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. NVIDIA-SMI NOT FOUND
   Problem: "nvidia-smi: command not found"
   
   Solutions:
   # Check driver installation
   $ lspci | grep -i nvidia
   $ dkms status
   
   # Reinstall driver
   $ sudo apt install nvidia-driver-535
   $ sudo reboot

2. CUDA OUT OF MEMORY
   Problem: "RuntimeError: CUDA out of memory"
   
   Solutions:
   # Check GPU memory
   $ nvidia-smi
   
   # Reduce batch size
   MAX_BATCH_SIZE=2
   
   # Clear cache
   import torch
   torch.cuda.empty_cache()

3. GPU NOT DETECTED IN VM
   Problem: GPU passthrough not working
   
   Solutions:
   # Check PCI passthrough config
   $ lspci -nnk | grep -i nvidia
   
   # Verify IOMMU enabled
   $ dmesg | grep -i iommu
   
   # Check VM config
   hostpci0: 01:00,pcie=1,rombar=1

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

NETWORK ISSUES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. CANNOT REACH SERVICE
   Problem: Connection timeout
   
   Debug:
   # Check service is running
   $ docker ps
   $ systemctl status <service>
   
   # Test connectivity
   $ telnet <host> <port>
   $ curl -v http://<host>:<port>/health
   
   # Check firewall
   $ sudo ufw status
   $ sudo iptables -L

2. DNS RESOLUTION FAILED
   Problem: "Could not resolve host"
   
   Solutions:
   # Check DNS
   $ cat /etc/resolv.conf
   $ nslookup <hostname>
   
   # Update DNS
   $ echo "nameserver 8.8.8.8" | sudo tee -a /etc/resolv.conf

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DIAGNOSTIC COMMANDS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

System Health:
$ htop                              # CPU/Memory
$ df -h                             # Disk usage
$ nvidia-smi                        # GPU status
$ docker stats                      # Container resources

Network:
$ netstat -tulpn                    # Open ports
$ ss -tulpn                         # Socket statistics
$ tcpdump -i any port 8000          # Network traffic

Logs:
$ journalctl -u docker -f           # Docker logs
$ docker logs -f <container>        # Container logs
$ tail -f /var/log/syslog          # System logs

EOF
11.2 Disaster Recovery Procedures
bash#!/bin/bash
# scripts/disaster_recovery.sh

# ============================================
# DISASTER RECOVERY PROCEDURES
# ============================================

set -euo pipefail

SCENARIO=${1:-""}

if [ -z "$SCENARIO" ]; then
    cat << EOF
Disaster Recovery Scenarios:

  complete_loss    - Complete infrastructure loss
  state_corrupted  - Terraform state corrupted
  server_failed    - Single server failure
  data_loss        - Database/storage loss
  network_outage   - Network connectivity loss

Usage: $0 <scenario>
EOF
    exit 1
fi

# ============================================
# SCENARIO 1: COMPLETE INFRASTRUCTURE LOSS
# ============================================

recover_complete_loss() {
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "DISASTER RECOVERY: Complete Infrastructure Loss"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    echo ""
    echo "STEP 1: Assess Situation"
    echo "  □ Confirm extent of damage"
    echo "  □ Check if backups are accessible"
    echo "  □ Verify state backups exist"
    echo ""
    read -p "Press Enter to continue..."
    
    echo ""
    echo "STEP 2: Restore Terraform State"
    echo "  $ aws s3 cp s3://ocr-terraform-state/production/terraform.tfstate ."
    echo "  or"
    echo "  $ cp backups/terraform_state/production_latest.tfstate.gz ."
    echo "  $ gunzip production_latest.tfstate.gz"
    echo ""
    read -p "State restored? (yes/no): " state_restored
    
    if [ "$state_restored" != "yes" ]; then
        echo "ERROR: Cannot proceed without state"
        exit 1
    fi
    
    echo ""
    echo "STEP 3: Re-provision Infrastructure"
    echo "  $ cd terraform/environments/production"
    echo "  $ terraform init"
    echo "  $ terraform plan"
    echo "  $ terraform apply"
    echo ""
    read -p "Provisioning complete? (yes/no): " provisioned
    
    echo ""
    echo "STEP 4: Configure Servers"
    echo "  $ cd ansible"
    echo "  $ ansible-playbook -i inventory/production/hosts.yml playbooks/site.yml"
    echo ""
    read -p "Configuration complete? (yes/no): " configured
    
    echo ""
    echo "STEP 5: Restore Data"
    echo "  Database:"
    echo "  $ gunzip -c /backups/db/latest.sql.gz | psql -h <db-host> -U postgres ocr_production"
    echo ""
    echo "  Files:"
    echo "  $ restic restore latest --target /var/app/uploads"
    echo ""
    read -p "Data restored? (yes/no): " data_restored
    
    echo ""
    echo "STEP 6: Deploy Applications"
    echo "  $ ansible-playbook playbooks/deploy_backends.yml"
    echo ""
    
    echo ""
    echo "STEP 7: Verify Services"
    echo "  $ ./scripts/health_check.sh"
    echo ""
    
    echo ""
    echo "✅ Recovery Complete!"
    echo ""
    echo "Next steps:"
    echo "  1. Run integration tests"
    echo "  2. Verify monitoring/alerting"
    echo "  3. Update documentation"
    echo "  4. Post-mortem meeting"
}

# ============================================
# SCENARIO 2: TERRAFORM STATE CORRUPTED
# ============================================

recover_state_corrupted() {
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "DISASTER RECOVERY: Terraform State Corrupted"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    echo ""
    echo "OPTION 1: Restore from Backup"
    echo "  $ cd terraform/environments/production"
    echo "  $ terraform state pull > corrupted.tfstate"
    echo "  $ cp backups/terraform_state/production_YYYYMMDD.tfstate terraform.tfstate"
    echo "  $ terraform state push terraform.tfstate"
    echo ""
    
    echo "OPTION 2: Rebuild State from Existing Infrastructure"
    echo "  $ terraform import proxmox_vm_qemu.gpu_server 101"
    echo "  $ terraform import proxmox_vm_qemu.cpu_server 102"
    echo "  $ terraform import proxmox_vm_qemu.database 103"
    echo ""
    
    echo "OPTION 3: Start Fresh (DANGEROUS)"
    echo "  1. Document all existing resources"
    echo "  2. terraform destroy (if state partially works)"
    echo "  3. Re-provision with terraform apply"
    echo ""
}

# ============================================
# SCENARIO 3: SINGLE SERVER FAILURE
# ============================================

recover_server_failed() {
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "DISASTER RECOVERY: Single Server Failure"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    read -p "Which server failed? (gpu/cpu/db): " server
    
    echo ""
    echo "STEP 1: Destroy Failed Server"
    echo "  $ terraform destroy -target=module.${server}_server"
    echo ""
    
    echo "STEP 2: Re-provision Server"
    echo "  $ terraform apply -target=module.${server}_server"
    echo ""
    
    echo "STEP 3: Configure Server"
    echo "  $ ansible-playbook -i inventory/production/hosts.yml playbooks/${server}_server.yml"
    echo ""
    
    if [ "$server" == "db" ]; then
        echo "STEP 4: Restore Database"
        echo "  $ ./scripts/restore_database.sh --latest"
        echo ""
    fi
    
    echo "STEP 5: Deploy Applications"
    echo "  $ ansible-playbook playbooks/deploy_backends.yml --limit ${server}_servers"
    echo ""
    
    echo "✅ Server recovery complete!"
}

# ============================================
# EXECUTE RECOVERY
# ============================================

case "$SCENARIO" in
    complete_loss)
        recover_complete_loss
        ;;
    state_corrupted)
        recover_state_corrupted
        ;;
    server_failed)
        recover_server_failed
        ;;
    *)
        echo "Unknown scenario: $SCENARIO"
        exit 1
        ;;
esac

12. 📋 CHECKLISTS & QUICK REFERENCE
12.1 Deployment Checklist
markdown# 🚀 DEPLOYMENT CHECKLIST

## PRE-DEPLOYMENT

### Code Review
- [ ] All changes peer-reviewed
- [ ] Tests passing (unit, integration, e2e)
- [ ] Security scan completed
- [ ] Performance benchmarks acceptable
- [ ] Documentation updated

### Infrastructure Review
- [ ] Terraform plan reviewed
- [ ] Ansible playbook tested in staging
- [ ] Resource capacity verified
- [ ] Backup plan confirmed
- [ ] Rollback plan documented

### Environment Preparation
- [ ] Staging environment matches production
- [ ] Database migrations tested
- [ ] Secrets/credentials verified
- [ ] SSL certificates valid
- [ ] DNS records configured

## DEPLOYMENT

### Pre-Deployment Steps
- [ ] Notify stakeholders (start maintenance window)
- [ ] Backup current state
```bash
  terraform state pull > backup.tfstate
  ./scripts/backup_database.sh
```
- [ ] Tag current version in Git
```bash
  git tag production-v1.2.3
  git push --tags
```

### Infrastructure Deployment
- [ ] Deploy Terraform changes
```bash
  cd terraform/environments/production
  terraform plan -out=tfplan
  terraform apply tfplan
```
- [ ] Run Ansible configuration
```bash
  ansible-playbook -i inventory/production/hosts.yml playbooks/site.yml
```
- [ ] Deploy applications
```bash
  ansible-playbook playbooks/deploy_backends.yml
```

### Post-Deployment Verification
- [ ] Health checks passing
```bash
  ./scripts/health_check.sh
```
- [ ] Smoke tests passing
- [ ] Monitoring dashboards green
- [ ] Logs show no errors
- [ ] Performance metrics acceptable

## POST-DEPLOYMENT

### Validation
- [ ] Integration tests passing
- [ ] End-to-end tests passing
- [ ] User acceptance testing (if applicable)
- [ ] Load testing (if major changes)

### Monitoring
- [ ] Alerts configured
- [ ] Dashboards updated
- [ ] Log aggregation working
- [ ] Metrics being collected

### Documentation
- [ ] Deployment notes documented
- [ ] Known issues documented
- [ ] Runbook updated (if needed)
- [ ] Team notified of changes

### Cleanup
- [ ] Close maintenance window
- [ ] Notify stakeholders (deployment complete)
- [ ] Remove old backups (keep recent)
- [ ] Update change log

## ROLLBACK PLAN

If deployment fails:

1. **Immediate Rollback**
```bash
   # Revert to previous Git tag
   git checkout production-v1.2.2
   
   # Restore Terraform state
   terraform state push backup.tfstate
   
   # Redeploy previous version
   ansible-playbook playbooks/deploy_backends.yml
```

2. **Database Rollback** (if migrations applied)
```bash
   ./scripts/restore_database.sh backup_pre_deploy.sql.gz
```

3. **Verify Rollback**
```bash
   ./scripts/health_check.sh
```

4. **Notify Team**
   - Inform stakeholders
   - Document what went wrong
   - Schedule post-mortem
12.2 Quick Command Reference
bash# ============================================
# QUICK COMMAND REFERENCE
# ============================================

# ==========================================
# TERRAFORM
# ==========================================

# Initialize
terraform init
terraform init -upgrade                    # Upgrade providers

# Plan & Apply
terraform plan                             # Preview changes
terraform plan -out=tfplan                 # Save plan
terraform apply tfplan                     # Execute plan
terraform apply -auto-approve              # Skip confirmation (dangerous!)

# State Management
terraform state list                       # List resources
terraform state show <resource>            # Show resource details
terraform state mv <src> <dst>             # Move resource
terraform state rm <resource>              # Remove from state
terraform state pull                       # Download state
terraform state push                       # Upload state

# Import & Destroy
terraform import <address> <id>            # Import existing resource
terraform destroy                          # Destroy all
terraform destroy -target=<resource>       # Destroy specific

# Workspaces
terraform workspace list                   # List workspaces
terraform workspace new <name>             # Create workspace
terraform workspace select <name>          # Switch workspace

# ==========================================
# ANSIBLE
# ==========================================

# Inventory
ansible-inventory --list                   # List inventory
ansible-inventory --graph                  # Show inventory tree

# Ad-hoc Commands
ansible all -m ping                        # Ping all hosts
ansible all -m shell -a "uptime"           # Run command
ansible all -m setup                       # Gather facts

# Playbooks
ansible-playbook playbook.yml              # Run playbook
ansible-playbook playbook.yml --check      # Dry run
ansible-playbook playbook.yml --diff       # Show differences
ansible-playbook playbook.yml --tags gpu   # Run specific tags
ansible-playbook playbook.yml --limit gpu_servers  # Limit to hosts

# Vault
ansible-vault create secrets.yml           # Create encrypted file
ansible-vault edit secrets.yml             # Edit encrypted file
ansible-vault encrypt file.yml             # Encrypt existing file
ansible-vault decrypt file.yml             # Decrypt file
ansible-playbook --ask-vault-pass          # Prompt for password

# ==========================================
# DOCKER
# ==========================================

# Containers
docker ps                                  # List running containers
docker ps -a                               # List all containers
docker logs -f <container>                 # Follow logs
docker exec -it <container> bash           # Shell into container
docker inspect <container>                 # Detailed info

# Images
docker images                              # List images
docker build -t name:tag .                 # Build image
docker pull <image>                        # Download image
docker push <image>                        # Upload image
docker rmi <image>                         # Remove image

# Docker Compose
docker-compose up -d                       # Start services
docker-compose down                        # Stop services
docker-compose logs -f                     # Follow logs
docker-compose ps                          # List services
docker-compose restart <service>           # Restart service
docker-compose build                       # Build images

# Cleanup
docker system prune                        # Remove unused resources
docker volume prune                        # Remove unused volumes
docker image prune -a                      # Remove unused images

# ==========================================
# SYSTEM
# ==========================================

# Process Management
systemctl status <service>                 # Service status
systemctl start <service>                  # Start service
systemctl stop <service>                   # Stop service
systemctl restart <service>                # Restart service
systemctl enable <service>                 # Enable on boot
journalctl -u <service> -f                 # Follow service logs

# Networking
netstat -tulpn                             # Open ports
ss -tulpn                                  # Socket stats
ufw status                                 # Firewall status
ufw allow 8000/tcp                         # Allow port

# GPU
nvidia-smi                                 # GPU status
nvidia-smi -l 1                            # Monitor GPU (1s interval)
nvidia-smi --query-gpu=... --format=csv    # Custom query

# ==========================================
# MONITORING
# ==========================================

# Prometheus
promtool check config prometheus.yml       # Validate config
promtool check rules alerts.yml            # Validate rules
curl http://localhost:9090/-/reload        # Reload config

# Docker Stats
docker stats                               # All containers
docker stats <container>                   # Specific container
12.3 Emergency Contact Card
yaml# emergency_contacts.yml

# ============================================
# EMERGENCY CONTACT CARD
# ============================================

incident_response:
  
  severity_levels:
    critical:
      description: "Complete system outage, data loss"
      response_time: "Immediate"
      escalation: "All teams + Management"
    
    high:
      description: "Major service degradation, security breach"
      response_time: "15 minutes"
      escalation: "Primary team + Team lead"
    
    medium:
      description: "Minor service issues, performance degradation"
      response_time: "1 hour"
      escalation: "Primary team"
    
    low:
      description: "Non-critical issues, monitoring alerts"
      response_time: "Next business day"
      escalation: "Individual engineer"

team_contacts:
  
  infrastructure_lead:
    name: "DevOps Lead"
    phone: "+49-xxx-xxx-xxxx"
    email: "devops-lead@company.com"
    slack: "@devops-lead"
    responsibility: "Infrastructure, Terraform, Ansible"
  
  backend_lead:
    name: "Backend Lead"
    phone: "+49-xxx-xxx-xxxx"
    email: "backend-lead@company.com"
    slack: "@backend-lead"
    responsibility: "OCR backends, Docker, Applications"
  
  database_admin:
    name: "DBA"
    phone: "+49-xxx-xxx-xxxx"
    email: "dba@company.com"
    slack: "@dba"
    responsibility: "PostgreSQL, Backups, Recovery"
  
  on_call:
    pagerduty: "https://company.pagerduty.com"
    phone: "+49-xxx-xxx-xxxx"
    schedule: "https://company.pagerduty.com/schedules"

external_contacts:
  
  proxmox_support:
    email: "support@proxmox.com"
    phone: "+43-xxx-xxx-xxxx"
    contract: "Premium Support"
  
  hosting_provider:
    name: "Hetzner"
    support: "https://hetzner.com/support"
    emergency: "+49-9831-505-0"

important_links:
  
  documentation:
    - "Infrastructure Wiki: https://wiki.company.com/infrastructure"
    - "Runbooks: https://wiki.company.com/runbooks"
    - "Architecture Diagrams: https://wiki.company.com/architecture"
  
  monitoring:
    - "Grafana: https://grafana.company.com"
    - "Prometheus: https://prometheus.company.com"
    - "Logs: https://logs.company.com"
  
  incident_management:
    - "PagerDuty: https://company.pagerduty.com"
    - "Status Page: https://status.company.com"
    - "Incident Channel: #incidents"

quick_actions:
  
  view_status:
    command: "./scripts/health_check.sh"
    description: "Check all services status"
  
  view_logs:
    command: "docker-compose logs -f --tail=100"
    description: "View application logs"
  
  restart_backend:
    command: "docker-compose restart backend-a-deepseek"
    description: "Restart GPU Backend A"
  
  emergency_rollback:
    command: "./scripts/rollback.sh production"
    description: "Rollback to previous version"
  
  restore_database:
    command: "./scripts/restore_database.sh --latest"
    description: "Restore from latest backup"

🎉 ZUSAMMENFASSUNG
markdown# INFRASTRUCTURE AS CODE - COMPLETE GUIDE SUMMARY

Du hast jetzt einen **vollständigen IaC Guide** für dein OCR-System!

## Was du bekommen hast:

### Teil 1: Grundlagen
✅ IaC Philosophie & Benefits
✅ Tool Stack (Terraform, Ansible, Docker)
✅ Projekt-Struktur

### Teil 2: Terraform
✅ Module für GPU/CPU/DB Server
✅ Netzwerk-Konfiguration
✅ Production Environment Setup
✅ State Management (S3 + DynamoDB)
✅ Management Scripts

### Teil 3: Ansible
✅ GPU Server Setup (NVIDIA Drivers, CUDA)
✅ Database Configuration (PostgreSQL)
✅ Backend Deployment
✅ Inventory Management

### Teil 4: Docker
✅ Docker Compose für GPU/CPU Server
✅ Multi-Backend Setup
✅ Nginx Reverse Proxy
✅ Monitoring (Prometheus + Grafana)

### Teil 5: GPU Configuration
✅ NVIDIA Driver Installation
✅ CUDA Setup
✅ GPU Monitoring
✅ Alert Rules

### Teil 6: Best Practices
✅ Golden Rules (Do's & Don'ts)
✅ Infrastructure Patterns
✅ Security Best Practices
✅ Troubleshooting Guide

### Teil 7: Operations
✅ Deployment Checklists
✅ Quick Command Reference
✅ Emergency Procedures
✅ Disaster Recovery

## Nächste Schritte:

1. **Setze State Backend auf**
```bash
   ./scripts/setup_state_backend.sh
```

2. **Provision Infrastructure**
```bash
   ./provision_infrastructure.sh production
```

3. **Deploy Backends**
```bash
   ansible-playbook playbooks/deploy_backends.yml
```

4. **Setup Monitoring**
   - Grafana Dashboards importieren
   - Alerts konfigurieren

5. **Test Everything**
```bash
   ./scripts/health_check.sh
```

## Production Ready! 🚀

Dein OCR-System kann jetzt:
- Komplett automatisch deployed werden
- In Minuten wiederhergestellt werden
- Multi-Environment (dev/staging/prod)
- Vollständig überwacht werden
- Sicher & skalierbar betrieben werden