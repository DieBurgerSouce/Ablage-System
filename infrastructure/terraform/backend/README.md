# Terraform Remote State Backend

Konfiguration für verteiltes Terraform State Management mit MinIO und PostgreSQL.

## Architektur

```
┌─────────────────┐    ┌─────────────────┐
│   Terraform     │───▶│     MinIO       │
│   (State I/O)   │    │  (S3 Storage)   │
└────────┬────────┘    └─────────────────┘
         │
         │ Lock/Unlock
         ▼
┌─────────────────┐
│   PostgreSQL    │
│  (Lock Table)   │
└─────────────────┘
```

## Dateien

| Datei | Beschreibung |
|-------|--------------|
| `backend.tf` | Terraform Backend-Konfiguration |
| `state-lock-table.sql` | PostgreSQL Locking-Tabelle |
| `minio-bucket-setup.sh` | MinIO Bucket-Einrichtung |
| `terraform-lock-wrapper.sh` | Wrapper mit Lock-Management |

## Setup

### 1. MinIO Bucket erstellen

```bash
export MINIO_ROOT_USER=admin
export MINIO_ROOT_PASSWORD=your-password
./minio-bucket-setup.sh
```

### 2. PostgreSQL Lock-Tabelle erstellen

```bash
psql -h localhost -U ablage_admin -d ablage_system -f state-lock-table.sql
```

### 3. Terraform initialisieren

```bash
cd ../
export AWS_ACCESS_KEY_ID=admin
export AWS_SECRET_ACCESS_KEY=your-password
terraform init -backend-config=environments/production/backend.hcl
```

## Verwendung

### Mit Lock-Wrapper (empfohlen für Produktion)

```bash
export PGPASSWORD=your-db-password
./backend/terraform-lock-wrapper.sh plan
./backend/terraform-lock-wrapper.sh apply
```

### Lock-Status prüfen

```bash
./backend/terraform-lock-wrapper.sh --status
./backend/terraform-lock-wrapper.sh --list
```

### Force-Unlock (Vorsicht!)

```bash
./backend/terraform-lock-wrapper.sh --force-unlock
```

## Umgebungen

| Umgebung | State Key | Beschreibung |
|----------|-----------|--------------|
| dev | `dev/terraform.tfstate` | Entwicklung |
| staging | `staging/terraform.tfstate` | Staging/Test |
| production | `production/terraform.tfstate` | Produktion |

## Fehlerbehebung

### Lock kann nicht erworben werden

1. Prüfe ob ein anderer Prozess läuft: `--list`
2. Warte bis Timeout (5 Min)
3. Im Notfall: `--force-unlock`

### State korrupt

1. State-Versionen in MinIO prüfen
2. Frühere Version wiederherstellen
3. `terraform refresh` ausführen
