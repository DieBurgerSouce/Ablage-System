# Ablage-System Deployment Guide

Dieses Dokument beschreibt die Bereitstellung des Ablage-Systems mit Ansible.

## Voraussetzungen

### Kontrollknoten (Ihr lokaler Rechner)

- Ansible 2.15+
- Python 3.11+
- SSH-Zugang zu den Zielservern

### Zielserver

- Ubuntu 22.04 LTS
- Mindestens 16 GB RAM
- NVIDIA GPU (RTX 4080 empfohlen) mit 16 GB VRAM
- 100 GB+ freier Festplattenspeicher
- Root-Zugang oder sudo-Berechtigungen

## Schnellstart

### 1. Ansible-Abhängigkeiten installieren

```bash
cd infrastructure/ansible
ansible-galaxy install -r requirements.yml
```

### 2. Inventory konfigurieren

Kopieren und anpassen Sie das Inventory für Ihre Umgebung:

```bash
# Für Produktion
cp inventories/production/group_vars/vault.yml.example inventories/production/group_vars/vault.yml

# Bearbeiten Sie die Vault-Datei
ansible-vault edit inventories/production/group_vars/vault.yml
```

### 3. SSH-Zugang testen

```bash
ansible -i inventories/production -m ping all
```

### 4. Vollständige Bereitstellung

```bash
ansible-playbook -i inventories/production playbooks/site.yml
```

## Playbook-Übersicht

| Playbook | Beschreibung | Verwendung |
|----------|--------------|------------|
| `site.yml` | Vollständige Bereitstellung | Erstinstallation |
| `provision.yml` | Server-Grundkonfiguration | Neue Server vorbereiten |
| `docker-setup.yml` | Docker + NVIDIA Setup | Container-Infrastruktur |
| `deploy.yml` | Anwendungs-Deployment | Updates deployen |
| `ssl-setup.yml` | SSL-Zertifikate | HTTPS konfigurieren |
| `backup.yml` | Backup erstellen | Datensicherung |
| `restore.yml` | Wiederherstellung | Daten wiederherstellen |
| `monitoring-setup.yml` | Monitoring-Stack | Überwachung einrichten |
| `rolling-update.yml` | Zero-Downtime-Updates | Ohne Ausfallzeit aktualisieren |
| `maintenance.yml` | Systemwartung | Aufräumen und optimieren |
| `health-check.yml` | Gesundheitsprüfung | System überprüfen |

## Bereitstellungsphasen

### Phase 1: Server-Provisionierung

```bash
ansible-playbook -i inventories/production playbooks/site.yml --tags provision
```

Dies installiert:
- Grundlegende System-Pakete
- Benutzer und Gruppen
- SSH-Härtung
- Firewall (UFW)
- Fail2ban
- Audit-Logging

### Phase 2: Docker & GPU

```bash
ansible-playbook -i inventories/production playbooks/site.yml --tags docker
```

Dies installiert:
- Docker CE
- Docker Compose
- NVIDIA-Treiber (Version 535)
- NVIDIA Container Toolkit

### Phase 3: SSL-Zertifikate

```bash
ansible-playbook -i inventories/production playbooks/ssl-setup.yml
```

Für manuelle Zertifikate, platzieren Sie diese unter:
```
/etc/ssl/ablage/
├── fullchain.pem
└── privkey.pem
```

### Phase 4: Anwendungs-Deployment

```bash
ansible-playbook -i inventories/production playbooks/deploy.yml
```

### Phase 5: Monitoring

```bash
ansible-playbook -i inventories/production playbooks/monitoring-setup.yml
```

### Phase 6: Backup & Health-Checks

```bash
ansible-playbook -i inventories/production playbooks/site.yml --tags backup,health
```

## Konfiguration

### Umgebungsvariablen

Hauptkonfigurationsdatei: `inventories/<env>/group_vars/all.yml`

```yaml
# Basis-Einstellungen
ablage_domain: ablage.example.com
ablage_install_dir: /opt/ablage-system
ablage_data_dir: /var/lib/ablage

# Benutzer
ablage_user: ablage
ablage_group: ablage

# Features
ssl_enabled: true
nvidia_driver_enabled: true
backup_enabled: true
```

### Vault-Variablen (Verschlüsselt)

Datei: `inventories/<env>/group_vars/vault.yml`

```yaml
# Passwörter
vault_db_password: <sicheres_passwort>
vault_secret_key: <jwt_geheimschlüssel>
vault_minio_secret_key: <minio_passwort>

# Admin
vault_admin_email: admin@example.com

# Optional: Remote-Backup
vault_backup_remote_user: backup
vault_backup_remote_host: backup.example.com
vault_backup_remote_path: /backups/ablage
```

## Updates durchführen

### Zero-Downtime-Update

```bash
ansible-playbook -i inventories/production playbooks/rolling-update.yml
```

Optionen:
```bash
# Nur Backend aktualisieren
ansible-playbook -i inventories/production playbooks/rolling-update.yml -e "update_frontend=false update_workers=false"

# Mit Neuaufbau der Container
ansible-playbook -i inventories/production playbooks/rolling-update.yml -e "force_rebuild=true"
```

### Schnelles Update (mit kurzer Ausfallzeit)

```bash
ansible-playbook -i inventories/production playbooks/deploy.yml
```

## Fehlerbehebung

### SSH-Verbindungsprobleme

```bash
# Verbindung testen
ansible -i inventories/production -m ping all -vvv

# Mit spezifischem SSH-Schlüssel
ansible -i inventories/production -m ping all --private-key ~/.ssh/ablage_key
```

### Docker-Probleme

```bash
# Container-Status prüfen
ansible -i inventories/production -m shell -a "cd /opt/ablage-system && docker compose ps" all

# Logs anzeigen
ansible -i inventories/production -m shell -a "cd /opt/ablage-system && docker compose logs --tail=50" all
```

### GPU-Probleme

```bash
# NVIDIA-Status prüfen
ansible -i inventories/production -m shell -a "nvidia-smi" all

# Container-Toolkit testen
ansible -i inventories/production -m shell -a "docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi" all
```

### Gesundheitsprüfung

```bash
ansible-playbook -i inventories/production playbooks/health-check.yml
```

## Sicherheit

### Vault-Passwort

Speichern Sie das Vault-Passwort sicher:

```bash
# In Datei speichern (nicht in Git!)
echo "IhrSicheresPasswort" > ~/.vault_pass
chmod 600 ~/.vault_pass

# In ansible.cfg konfigurieren
vault_password_file = ~/.vault_pass
```

### SSH-Schlüssel

Verwenden Sie dedizierte SSH-Schlüssel für Ansible:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/ablage_ansible -C "ansible@ablage"
ssh-copy-id -i ~/.ssh/ablage_ansible.pub benutzer@server
```

## Verzeichnisstruktur

```
infrastructure/ansible/
├── ansible.cfg              # Ansible-Konfiguration
├── requirements.yml         # Galaxy-Abhängigkeiten
├── inventories/
│   ├── dev/                 # Entwicklung
│   ├── staging/             # Staging
│   └── production/          # Produktion
│       ├── hosts.yml        # Host-Definition
│       └── group_vars/
│           ├── all.yml      # Allgemeine Variablen
│           └── vault.yml    # Verschlüsselte Secrets
├── playbooks/
│   ├── site.yml             # Master-Playbook
│   ├── provision.yml        # Server-Setup
│   ├── deploy.yml           # App-Deployment
│   └── ...
└── roles/
    ├── common/              # Basis-Konfiguration
    ├── security/            # Sicherheitshärtung
    ├── docker/              # Docker-Installation
    ├── nvidia/              # GPU-Treiber
    ├── ssl-certificates/    # SSL-Verwaltung
    ├── ablage-deploy/       # App-Deployment
    ├── logrotate/           # Log-Rotation
    ├── backup/              # Backup-System
    ├── monitoring/          # Monitoring-Stack
    └── health-checks/       # Gesundheitsprüfungen
```

## Support

Bei Problemen:

1. Logs prüfen: `journalctl -u ablage-system -f`
2. Gesundheitsprüfung: `/usr/local/bin/ablage-health-check`
3. Docker-Status: `docker compose ps`
4. GPU-Status: `nvidia-smi`
