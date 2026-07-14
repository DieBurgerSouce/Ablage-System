# Häufig gestellte Fragen (FAQ)

Antworten auf die häufigsten Fragen zu Ablage-System OCR.

---

## Allgemein

### Was ist Ablage-System OCR?

Ablage-System OCR ist eine Enterprise-grade Plattform für die Digitalisierung deutscher Dokumente mit GPU-beschleunigtem OCR. Das System bietet drei spezialisierte OCR-Backends und ist für On-Premises-Deployment optimiert.

### Für wen ist Ablage-System geeignet?

- **Unternehmen** mit hohem Dokumentenaufkommen
- **Behörden** mit Datenschutzanforderungen
- **Archive** mit historischen Dokumenten (Frakturschrift)
- **Organisationen** die On-Premises-Lösungen benötigen
- **Entwickler** die OCR-APIs integrieren möchten

### Warum On-Premises statt Cloud?

- **Datenschutz**: Alle Daten bleiben lokal
- **GDPR/DSGVO-Compliance**: Vollständige Kontrolle
- **Keine laufenden Kosten**: Keine Cloud-API-Gebühren
- **Keine Abhängigkeiten**: Funktioniert offline
- **Performance**: Direkter GPU-Zugriff

---

## Installation & Setup

### Welche Hardware-Anforderungen gibt es?

**Minimum (Entwicklung)**:
- CPU: 4 Kerne
- RAM: 16 GB
- Disk: 100 GB SSD
- GPU: Optional (CPU-Fallback)

**Empfohlen (Produktion)**:
- CPU: 8+ Kerne
- RAM: 32+ GB
- Disk: 500+ GB NVMe SSD
- GPU: NVIDIA RTX 4080 oder besser (16GB+ VRAM)

[:octicons-arrow-right-24: Detaillierte Anforderungen](installation/prerequisites.md)

### Kann ich Ablage-System ohne GPU betreiben?

Ja! Alle OCR-Backends haben CPU-Fallback-Modi:

- **DeepSeek-Janus-Pro**: CPU-Modus mit reduzierter Performance
- **GOT-OCR 2.0**: CPU-Modus verfügbar
- **Surya+Docling**: Native CPU-Unterstützung

⚠️ **Hinweis**: CPU-Verarbeitung ist ~5-10x langsamer als GPU.

### Welche GPUs werden unterstützt?

**Unterstützt**:
- NVIDIA RTX 4090, 4080, 4070 (Ada Lovelace)
- NVIDIA RTX 3090, 3080, 3070 (Ampere)
- NVIDIA A100, A40, A30 (Data Center)
- Tesla V100, P100 (mit Einschränkungen)

**Mindestanforderung**:
- CUDA Compute Capability 7.0+
- 8GB+ VRAM (12GB+ empfohlen)

**Nicht unterstützt**:
- AMD GPUs (derzeit keine ROCm-Unterstützung)
- Intel Arc GPUs

[:octicons-arrow-right-24: GPU-Setup-Guide](installation/gpu-setup.md)

### Funktioniert Ablage-System unter Windows?

Ja, mit Einschränkungen:

- **WSL2**: Vollständig unterstützt (empfohlen)
- **Native Windows**: Docker Desktop erforderlich
- **GPU-Support**: Nur mit WSL2 + CUDA

**Empfehlung**: Ubuntu 22.04 LTS für Produktion

### Wie lange dauert die Installation?

- **Docker Compose**: 5-10 Minuten
- **Lokale Entwicklung**: 15-20 Minuten
- **Terraform (Produktion)**: 30-45 Minuten

Erste Startzeit: 2-5 Minuten (OCR-Modelle werden heruntergeladen, ~15GB)

---

## OCR-Backends

### Welches OCR-Backend soll ich verwenden?

**Automatische Auswahl** (empfohlen):
```python
OCR_DEFAULT_BACKEND=auto
```

**Manuelle Auswahl**:

| Backend | Use Case | Performance | Genauigkeit |
|---------|----------|-------------|-------------|
| **DeepSeek** | Komplexe Layouts, Tabellen | 2-3 S/s | 99.5% |
| **GOT-OCR** | Schnelle Verarbeitung | 5-7 S/s | 98.8% |
| **Surya** | CPU-only, Layout-Analyse | 1-2 S/s | 97.5% |

[:octicons-arrow-right-24: Backend-Vergleich](ocr-engines/comparison.md)

### Wie gut ist die Deutsche Texterkennung?

**Genauigkeit**:
- Standard-Dokumente: 98-99%
- Frakturschrift: 95-97%
- Handschrift: 70-85% (experimentell)
- Umlaute (ä,ö,ü,ß): 100%

**Optimiert für**:
- Rechnungen
- Verträge
- Formulare
- Amtliche Dokumente
- Historische Texte

### Kann ich eigene OCR-Modelle hinzufügen?

Ja! Ablage-System ist erweiterbar:

```python
from app.services.ocr.base import OCRBackend

class CustomOCR(OCRBackend):
    def process(self, image):
        # Ihre OCR-Logik
        return result
```

[:octicons-arrow-right-24: Custom OCR-Tutorial](tutorials/add-ocr-engine.md)

### Unterstützt Ablage-System Handschriftenerkennung?

**Experimentell**: Ja, mit DeepSeek-Janus-Pro

- Gedruckte Formulare mit handschriftlichen Einträgen
- Deutlich lesbare Handschrift
- Genauigkeit: 70-85%

⚠️ **Limitierungen**:
- Keine Kursivschrift
- Keine unleserliche Handschrift
- Englisch besser als Deutsch

---

## Performance & Skalierung

### Wie viele Dokumente kann ich pro Stunde verarbeiten?

**Mit RTX 4080 (empfohlen)**:
- DeepSeek: ~150-200 Seiten/Stunde
- GOT-OCR: ~300-420 Seiten/Stunde
- Surya: ~60-120 Seiten/Stunde

**Batch-Verarbeitung** (32 Dokumente parallel):
- bis zu 500+ Seiten/Stunde

**CPU-Modus**:
- ~50-100 Seiten/Stunde

### Kann Ablage-System horizontal skalieren?

Ja! Architektur ist für Skalierung designed:

- **Backend**: Stateless, beliebig viele Instanzen
- **Worker**: Ein Worker pro GPU
- **Datenbank**: Read Replicas
- **Storage**: MinIO Cluster

**Beispiel-Setup (High Volume)**:
- 3x Backend-Server
- 5x Worker-Server (jeweils mit GPU)
- 1x Database Primary + 2x Replicas
- 4-Node MinIO Cluster

= ~2500 Seiten/Stunde

[:octicons-arrow-right-24: Skalierungs-Guide](operations/scaling.md)

### Wie kann ich die Performance verbessern?

**GPU-Optimierung**:
```bash
# Batch-Size erhöhen
export OCR_MAX_BATCH_SIZE=64

# GPU-Memory-Fraction anpassen
export GPU_MEMORY_FRACTION=0.90
```

**Backend-Auswahl**:
- GOT-OCR für Geschwindigkeit
- DeepSeek für Genauigkeit

**Infrastruktur**:
- NVMe SSDs für Storage
- 10GbE Netzwerk
- Mehr Worker-GPUs

[:octicons-arrow-right-24: Performance-Tuning](performance/gpu-optimization.md)

---

## Sicherheit & Datenschutz

### Ist Ablage-System GDPR/DSGVO-konform?

Ja! Ablage-System ist für GDPR-Compliance designed:

- ✅ On-Premises (keine Cloud)
- ✅ Datenlöschung nach Aufbewahrungsfrist
- ✅ Datenexport (Portabilität)
- ✅ Audit-Logging
- ✅ Verschlüsselung (Transit + Rest)
- ✅ Zugriffskontrollen

[:octicons-arrow-right-24: GDPR-Compliance](security/compliance.md)

### Wie werden Secrets verwaltet?

Mit **HashiCorp Vault**:

- Zentrales Secret Management
- Automatische Rotation
- Zugriffsrichtlinien
- Audit-Logging
- Verschlüsselte Speicherung

```bash
# Secret abrufen
vault kv get secret/ablage-system/database
```

[:octicons-arrow-right-24: Secret Management](infrastructure/vault/secret-management.md)

### Welche Authentifizierungsmethoden werden unterstützt?

**Aktuell**:
- JWT Token-basiert
- Username/Password
- API Keys

**Geplant** (v1.1+):
- SAML 2.0
- OIDC/OAuth 2.0
- LDAP/Active Directory
- Multi-Factor Authentication (MFA)

### Sind die Dokumente verschlüsselt?

Ja, mehrfach:

**In Transit**:
- TLS 1.3 für alle API-Kommunikation
- Verschlüsselte interne Kommunikation

**At Rest**:
- MinIO Server-Side Encryption (AES-256)
- PostgreSQL Transparent Data Encryption
- Optional: Full Disk Encryption

[:octicons-arrow-right-24: Verschlüsselung](security/encryption.md)

---

## Betrieb & Wartung

### Wie überwache ich Ablage-System?

**Monitoring-Stack**:
- **Prometheus**: Metriken-Sammlung
- **Grafana**: Visualisierung
- **Sentry**: Error Tracking
- **Alertmanager**: Benachrichtigungen

**Key Metrics**:
- OCR-Verarbeitungszeit
- GPU-Auslastung
- Queue-Länge
- API Response Time
- Error Rate

Grafana-Dashboards sind vorkonfiguriert.

[:octicons-arrow-right-24: Monitoring-Setup](operations/monitoring.md)

### Wie mache ich Backups?

**Automatisches Backup**:
```bash
# Daily backup (restic — siehe docs/runbooks/disaster-recovery.md §1)
0 2 * * * bash /opt/ablage-system/scripts/backup/restic_backup.sh
```

**Backup enthält**:
- PostgreSQL-Datenbank
- MinIO-Dokumente
- Vault-Secrets (verschlüsselt)
- Konfigurationsdateien

**Retention**: 30 Tage (konfigurierbar)

[:octicons-arrow-right-24: Backup & Restore](operations/backup-restore.md)

### Was passiert bei GPU-Ausfall?

**Automatischer Fallback**:
1. GPU-Fehler wird erkannt
2. Task wird neu eingeplant
3. CPU-Verarbeitung startet
4. Benachrichtigung gesendet

**Konfiguration**:
```python
GPU_FALLBACK_ENABLED=true
GPU_FALLBACK_THRESHOLD=3  # Nach 3 Fehlern
```

### Wie führe ich Updates durch?

**Docker Compose**:
```bash
docker-compose pull
docker-compose up -d
```

**Zero-Downtime-Update**:
1. Blue-Green Deployment
2. Rolling Updates
3. Database Migrations automatisch

[:octicons-arrow-right-24: Update-Prozess](operations/maintenance.md)

---

## Entwicklung & Integration

### Wie integriere ich Ablage-System in meine Anwendung?

**REST API**:
```python
import requests

# Dokument hochladen
files = {"file": open("document.pdf", "rb")}
response = requests.post(
    "https://api.ablage-system.local/api/v1/documents/",
    files=files,
    headers={"Authorization": f"Bearer {token}"}
)
doc_id = response.json()["id"]

# Ergebnis abrufen
result = requests.get(
    f"https://api.ablage-system.local/api/v1/documents/{doc_id}",
    headers={"Authorization": f"Bearer {token}"}
)
```

[:octicons-arrow-right-24: API-Dokumentation](api/overview.md)

### Gibt es SDKs für andere Sprachen?

**Geplant**:
- Python SDK (v1.1)
- JavaScript/TypeScript SDK (v1.2)
- Go SDK (v1.3)
- Java SDK (v2.0)

**Aktuell**: REST API mit OpenAPI 3.1 Spec

### Kann ich Webhooks verwenden?

Ja! Webhook-Benachrichtigungen für:

- Dokument hochgeladen
- OCR-Verarbeitung abgeschlossen
- Fehler aufgetreten
- Dokument gelöscht

```python
WEBHOOK_URL=https://your-app.com/webhooks/ablage
WEBHOOK_EVENTS=document.processed,document.failed
```

[:octicons-arrow-right-24: Webhook-Integration](tutorials/webhook-integration.md)

### Wie kann ich zur Entwicklung beitragen?

Wir freuen uns über Beiträge!

1. Fork des Repository
2. Feature Branch erstellen
3. Tests schreiben
4. Pull Request öffnen

[:octicons-arrow-right-24: Contributing Guide](contributing/guide.md)

---

## Fehlerbehandlung

### "GPU not detected" - Was tun?

1. **NVIDIA-Treiber prüfen**:
   ```bash
   nvidia-smi
   ```

2. **Container Toolkit prüfen**:
   ```bash
   docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi
   ```

3. **Logs checken**:
   ```bash
   docker-compose logs backend
   ```

[:octicons-arrow-right-24: GPU Troubleshooting](operations/troubleshooting.md#gpu-probleme)

### "Database connection failed" - Lösung?

1. **PostgreSQL-Status prüfen**:
   ```bash
   docker-compose ps postgres
   ```

2. **Verbindung testen**:
   ```bash
   docker exec -it ablage-postgres psql -U ablage_user
   ```

3. **Logs ansehen**:
   ```bash
   docker-compose logs postgres
   ```

### "OCR processing timeout" - Warum?

**Häufige Ursachen**:
- Dokument zu groß (>50MB)
- Komplexes Layout
- GPU-Memory voll
- Worker überlastet

**Lösungen**:
- Timeout erhöhen: `OCR_TIMEOUT_SECONDS=600`
- Batch-Size reduzieren: `OCR_MAX_BATCH_SIZE=16`
- Mehr Worker starten

### Wo finde ich Logs?

**Docker Compose**:
```bash
# Alle Services
docker-compose logs -f

# Spezifischer Service
docker-compose logs -f backend
docker-compose logs -f worker

# Letzte 100 Zeilen
docker-compose logs --tail=100 backend
```

**Produktions-Setup**:
```bash
# Systemd Services
journalctl -u ablage-backend -f
journalctl -u ablage-worker -f

# Log-Dateien
tail -f /var/log/ablage-system/backend.log
```

---

## Lizenzierung & Support

### Welche Lizenz hat Ablage-System?

**MIT-Lizenz** - frei und Open Source

- ✅ Kommerzielle Nutzung
- ✅ Modifikation
- ✅ Distribution
- ✅ Private Nutzung

[:octicons-arrow-right-24: Lizenz-Details](https://opensource.org/licenses/MIT)

### Gibt es professionellen Support?

**Community Support** (kostenlos):
- GitHub Issues
- Community Forum
- Dokumentation

**Enterprise Support** (geplant):
- 24/7 Support
- SLA-Garantien
- Dedizierter Support Engineer
- Custom Development
- Training & Consulting

📧 Kontakt: [enterprise@ablage-system.local](mailto:enterprise@ablage-system.local)

### Wo kann ich Bugs melden?

**GitHub Issues**: [github.com/ablage-system/ablage-system-ocr/issues](https://github.com/ablage-system/ablage-system-ocr/issues)

**Bitte angeben**:
- Ablage-System Version
- Betriebssystem
- GPU-Modell (falls relevant)
- Fehlermeldung/Logs
- Reproduktionsschritte

---

## Roadmap

### Welche Features kommen als nächstes?

**Version 1.1 (Q2 2025)**:
- Kubernetes-Support
- Multi-GPU-Unterstützung
- Python SDK
- GraphQL API
- Mobile App

**Version 2.0 (Q3 2025)**:
- AI-Dokumentenklassifizierung
- Automatische Formularerkennung
- Multi-Tenant-Unterstützung
- SAML/OIDC Integration
- Advanced Analytics

[:octicons-arrow-right-24: Vollständige Roadmap](roadmap.md)

### Kann ich Feature-Requests einreichen?

Ja! Nutzen Sie GitHub Discussions oder Issues:

1. Feature-Request öffnen
2. Use Case beschreiben
3. Community diskutiert
4. Team priorisiert

---

## Weitere Fragen?

Frage nicht gefunden?

- 📖 **Dokumentation durchsuchen**: Nutzen Sie die Suchfunktion (Ctrl+K)
- 💬 **Community Forum**: [forum.ablage-system.local](https://forum.ablage-system.local)
- 🐛 **GitHub Issues**: [github.com/ablage-system/ablage-system-ocr/issues](https://github.com/ablage-system/ablage-system-ocr/issues)
- 📧 **Email**: [support@ablage-system.local](mailto:support@ablage-system.local)
