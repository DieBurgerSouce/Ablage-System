# Schnellstart-Anleitung

> In 5 Minuten zum ersten OCR-Ergebnis mit dem Ablage-System

## Voraussetzungen

- Docker und Docker Compose installiert
- NVIDIA GPU mit mindestens 8GB VRAM (optional, aber empfohlen)
- Git installiert

## Schritt 1: Repository klonen

```bash
git clone https://github.com/your-org/ablage-system.git
cd ablage-system
```

## Schritt 2: Umgebung konfigurieren

```bash
# Beispiel-Konfiguration kopieren
cp .env.example .env
```

Fuer den Schnellstart sind die Standardwerte ausreichend. Fuer Produktion siehe [DEPLOYMENT.md](./DEPLOYMENT.md).

## Schritt 3: System starten

```bash
# Alle Services starten
docker compose up -d

# Warten bis alle Services bereit sind (ca. 1-2 Minuten)
docker compose logs -f backend
# Warten auf: "Uvicorn running on http://0.0.0.0:8000"
```

## Schritt 4: Datenbank initialisieren

```bash
# Datenbankschema erstellen
docker compose exec backend alembic upgrade head
```

## Schritt 5: System testen

```bash
# Health-Check
curl http://localhost:8000/health
# Erwartete Antwort: {"status": "healthy", ...}

# API-Dokumentation oeffnen
# Browser: http://localhost:8000/docs
```

## Schritt 6: Erstes Dokument verarbeiten

### Option A: Web-Oberflaeche

1. Browser oeffnen: `http://localhost:80`
2. Dokument per Drag & Drop hochladen
3. OCR-Ergebnis ansehen

### Option B: API

```bash
# Dokument hochladen
curl -X POST "http://localhost:8000/api/v1/documents/" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@mein-dokument.pdf"

# Antwort enthaelt document_id
# {"id": "abc123", "status": "pending", ...}

# OCR starten
curl -X POST "http://localhost:8000/api/v1/ocr/abc123/process"

# Status pruefen
curl "http://localhost:8000/api/v1/documents/abc123"
# {"id": "abc123", "status": "completed", "extracted_text": "...", ...}
```

## Naechste Schritte

- [ARCHITECTURE.md](./ARCHITECTURE.md) - Systemarchitektur verstehen
- [API_REFERENCE.md](./API_REFERENCE.md) - Vollstaendige API-Dokumentation
- [DEPLOYMENT.md](./DEPLOYMENT.md) - Produktions-Deployment
- [CLAUDE.md](./CLAUDE.md) - Detaillierte Entwicklerdokumentation

## Haeufige Probleme

### GPU wird nicht erkannt

```bash
# NVIDIA Container Toolkit pruefen
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi

# Falls nicht funktioniert: NVIDIA Container Toolkit installieren
# Siehe: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html
```

### Port 80 bereits belegt

```bash
# Alternativen Port verwenden
# In docker-compose.yml:
# ports:
#   - "8080:80"  # Statt "80:80"
```

### Nicht genug Speicher

```bash
# In .env:
MAX_GPU_MEMORY_PERCENT=70
MAX_BATCH_SIZE=2
```

## Support

Bei Fragen oder Problemen:
- GitHub Issues: https://github.com/your-org/ablage-system/issues
- Dokumentation: [CLAUDE.md](./CLAUDE.md)

---

*Viel Erfolg mit dem Ablage-System!*
