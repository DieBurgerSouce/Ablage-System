# Ablage-System Infrastructure

Enterprise-grade Infrastructure as Code für das Ablage-System OCR Platform.

## Übersicht

```
infrastructure/
├── terraform/           # Infrastructure as Code
│   ├── backend/         # Remote State (MinIO + PostgreSQL)
│   ├── proxmox/         # Proxmox VE Virtualisierung
│   └── environments/    # Umgebungsspezifische Konfiguration
├── ansible/             # Configuration Management
│   ├── roles/           # Ansible Roles
│   │   ├── k3s-server/  # K3s Master Node
│   │   ├── k3s-agent/   # K3s Worker Nodes
│   │   └── k3s-gpu-node/# GPU Node mit NVIDIA Support
│   └── playbooks/       # Deployment Playbooks
├── kubernetes/          # Kubernetes Manifests
│   └── base/            # Base Kustomize Manifests
│       ├── backend/     # FastAPI Backend
│       ├── worker/      # GPU Worker
│       ├── frontend/    # Nginx Frontend
│       ├── postgres/    # PostgreSQL 16
│       ├── redis/       # Redis 7
│       ├── minio/       # MinIO Object Storage
│       └── network-policies/
├── helm/                # Helm Charts
│   └── ablage-system/   # Main Application Chart
│       ├── templates/   # Kubernetes Templates
│       ├── values.yaml  # Default Values
│       └── values-production.yaml
└── gitops/              # GitOps Configuration
    ├── argocd/          # ArgoCD Applications
    └── fluxcd/          # FluxCD Automation
```

## Quick Start

### 1. Terraform Remote State einrichten

```bash
cd infrastructure/terraform/backend
./minio-bucket-setup.sh
psql -f state-lock-table.sql
```

### 2. K3s Cluster installieren

```bash
cd infrastructure/ansible
ansible-playbook -i inventory/production playbooks/k3s-install.yml
```

### 3. Ablage-System mit Helm deployen

```bash
helm upgrade --install ablage-system infrastructure/helm/ablage-system \
  -f infrastructure/helm/ablage-system/values.yaml \
  --namespace ablage-system \
  --create-namespace
```

### 4. GitOps aktivieren

```bash
ansible-playbook playbooks/gitops-install.yml
```

## Komponenten

### Terraform
- **Remote State**: MinIO (S3-kompatibel) mit PostgreSQL für State Locking
- **Proxmox Provider**: VM-Provisionierung für K3s Nodes
- **Umgebungen**: dev, staging, production

### Ansible Roles
- **k3s-server**: K3s Control Plane mit Metrics Server, Ingress-Nginx
- **k3s-agent**: K3s Worker Nodes
- **k3s-gpu-node**: NVIDIA Container Toolkit, GPU Device Plugin

### Kubernetes
- **Deployments**: Backend (2 Replicas), Worker (GPU), Frontend
- **StatefulSets**: PostgreSQL, Redis, MinIO
- **HPA**: Auto-Scaling für Backend (2-5 Replicas)
- **Network Policies**: Zero-Trust Networking
- **Resource Quotas**: CPU/Memory Limits pro Namespace

### Helm Chart
- Vollständiges Application Deployment
- Konfigurierbare Values für alle Umgebungen
- Bitnami Dependencies (optional)
- GPU Worker Support mit Tolerations

### GitOps
- **ArgoCD**: Application Deployment, Multi-Environment
- **FluxCD**: Image Automation, Semantic Versioning
- **Notifications**: Slack Integration

## GPU Konfiguration

Der Worker benötigt GPU-Zugriff (RTX 4080, 16GB VRAM):

```yaml
worker:
  gpu:
    enabled: true
    count: 1
    type: nvidia.com/gpu
  nodeSelector:
    nvidia.com/gpu.present: "true"
  tolerations:
    - key: "nvidia.com/gpu"
      operator: "Exists"
      effect: "NoSchedule"
```

## Sicherheit

- Network Policies: Default Deny, explizite Allow-Rules
- Secrets Management: External Secrets empfohlen
- RBAC: ServiceAccounts mit minimalen Rechten
- Pod Security: Non-root Container

## Monitoring

- Prometheus Scraping aktiviert
- Metrics Endpoints:
  - Backend: `:8000/metrics`
  - PostgreSQL: `:9187/metrics`
  - Redis: `:9121/metrics`

## Wartung

### Helm Upgrade
```bash
helm upgrade ablage-system infrastructure/helm/ablage-system \
  --reuse-values \
  --set backend.image.tag=v1.1.0
```

### Rollback
```bash
helm rollback ablage-system 1
```

### Status prüfen
```bash
kubectl get pods -n ablage-system
kubectl get events -n ablage-system --sort-by='.lastTimestamp'
```

---

*Feinpoliert und durchdacht - Enterprise Document Processing*
