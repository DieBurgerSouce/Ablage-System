# Ablage-System Ansible Automation

Enterprise-grade Ansible automation for deploying and managing the Ablage-System document processing platform.

## Quick Start

```bash
# 1. Install dependencies
ansible-galaxy install -r requirements.yml

# 2. Configure inventory
cp inventories/production/group_vars/vault.yml.example inventories/production/group_vars/vault.yml
ansible-vault edit inventories/production/group_vars/vault.yml

# 3. Test connection
ansible -i inventories/production -m ping all

# 4. Deploy
ansible-playbook -i inventories/production playbooks/site.yml
```

## Structure

```
ansible/
├── ansible.cfg                 # Ansible configuration
├── requirements.yml            # Galaxy dependencies
├── DEPLOYMENT.md               # Deployment guide
├── BACKUP_RESTORE.md           # Backup/restore guide
├── inventories/
│   ├── dev/                    # Development environment
│   ├── staging/                # Staging environment
│   └── production/             # Production environment
├── playbooks/
│   ├── site.yml                # Master playbook
│   ├── provision.yml           # Server setup
│   ├── docker-setup.yml        # Docker + GPU
│   ├── deploy.yml              # App deployment
│   ├── ssl-setup.yml           # SSL certificates
│   ├── backup.yml              # Create backups
│   ├── restore.yml             # Restore from backup
│   ├── monitoring-setup.yml    # Monitoring stack
│   ├── rolling-update.yml      # Zero-downtime update
│   ├── maintenance.yml         # System maintenance
│   └── health-check.yml        # Health verification
└── roles/
    ├── common/                 # Base system config
    ├── security/               # Security hardening
    ├── docker/                 # Docker installation
    ├── nvidia/                 # GPU drivers
    ├── ssl-certificates/       # SSL management
    ├── ablage-deploy/          # App deployment
    ├── logrotate/              # Log rotation
    ├── backup/                 # Backup system
    ├── monitoring/             # Monitoring stack
    └── health-checks/          # Health monitoring
```

## Playbooks

| Playbook | Purpose | Usage |
|----------|---------|-------|
| `site.yml` | Complete deployment | `ansible-playbook -i inv/prod playbooks/site.yml` |
| `provision.yml` | Server provisioning | New server setup |
| `docker-setup.yml` | Docker + NVIDIA | Container infrastructure |
| `deploy.yml` | Application deployment | Deploy updates |
| `ssl-setup.yml` | SSL certificates | HTTPS configuration |
| `backup.yml` | Create backup | Data protection |
| `restore.yml` | Restore backup | Disaster recovery |
| `monitoring-setup.yml` | Monitoring | Prometheus + Grafana |
| `rolling-update.yml` | Zero-downtime update | Production updates |
| `maintenance.yml` | System maintenance | Cleanup + optimize |
| `health-check.yml` | Health check | System verification |

## Roles

| Role | Description |
|------|-------------|
| `common` | Base packages, users, kernel tuning, timezone |
| `security` | SSH hardening, UFW, fail2ban, audit logging |
| `docker` | Docker CE, daemon config, NVIDIA runtime |
| `nvidia` | NVIDIA driver 535, Container Toolkit |
| `ssl-certificates` | Manual cert deployment, DH params |
| `ablage-deploy` | App sync, .env generation, migrations |
| `logrotate` | Docker + app log rotation |
| `backup` | PostgreSQL, Redis, MinIO backups |
| `monitoring` | Node/GPU exporters, Grafana dashboards |
| `health-checks` | Health scripts, alerting |

## Requirements

### Control Node
- Ansible 2.15+
- Python 3.11+
- SSH access to targets

### Target Servers
- Ubuntu 22.04 LTS
- 16 GB+ RAM
- NVIDIA GPU (RTX 4080 recommended)
- 100 GB+ disk space

## Configuration

### Environment Variables (all.yml)

```yaml
ablage_domain: ablage.example.com
ablage_install_dir: /opt/ablage-system
ssl_enabled: true
nvidia_driver_enabled: true
backup_enabled: true
```

### Secrets (vault.yml)

```yaml
vault_db_password: <secure_password>
vault_secret_key: <jwt_secret>
vault_minio_secret_key: <minio_password>
vault_admin_email: admin@example.com
```

## Common Operations

```bash
# Full deployment
ansible-playbook -i inventories/production playbooks/site.yml

# Update application only
ansible-playbook -i inventories/production playbooks/deploy.yml

# Zero-downtime update
ansible-playbook -i inventories/production playbooks/rolling-update.yml

# Create backup
ansible-playbook -i inventories/production playbooks/backup.yml

# System maintenance
ansible-playbook -i inventories/production playbooks/maintenance.yml

# Health check
ansible-playbook -i inventories/production playbooks/health-check.yml
```

## Tags

Use tags for partial deployments:

```bash
# Provision only
ansible-playbook -i inv/prod playbooks/site.yml --tags provision

# Docker + GPU only
ansible-playbook -i inv/prod playbooks/site.yml --tags docker

# Skip monitoring
ansible-playbook -i inv/prod playbooks/site.yml --skip-tags monitoring
```

## Documentation

- [Deployment Guide](DEPLOYMENT.md) - Full deployment instructions
- [Backup & Restore](BACKUP_RESTORE.md) - Data protection procedures

## License

Proprietary - Internal use only
