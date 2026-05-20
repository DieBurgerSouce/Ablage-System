# Qdrant A/B Testing - Aktivierungsanleitung

## ⚠️ WICHTIG: Langfristige Skalierungsstrategie

### Erwartetes Wachstum (Stand: Dezember 2024)
| Zeitraum | Dokumente | Vektoren (geschätzt) |
|----------|-----------|---------------------|
| Aktuell | ~100 | 674 |
| Jahr 1 (2025) | 200.000 | 1-2 Millionen |
| Danach | +20-30k/Jahr | +100-200k Vektoren/Jahr |

### 🎯 SKALIERUNGS-ROADMAP

| Phase | Dokumente | Traffic Split | Aktion |
|-------|-----------|---------------|--------|
| 1 | 0 - 10k | 10% Qdrant | Monitoring, Bugs finden |
| 2 | 10k - 50k | 25% → 50% | Performance vergleichen |
| 3 | 50k - 100k | 75% → 100% | pgvector als Backup |
| 4 | 100k+ | 100% Qdrant | Full Rollout |

**Bei jedem Besuch prüfen:**
1. Dokumenten-Anzahl checken
2. Traffic-Split entsprechend anpassen
3. Performance-Metriken vergleichen (Latenz, Error-Rate)

---

Dieses Dokument beschreibt die Aktivierung und Konfiguration des A/B Testing zwischen **pgvector** (Control) und **Qdrant** (Treatment) für die Vektor-Suche.

## Überblick

Das A/B Testing System ermöglicht:
- Performance-Vergleich zwischen pgvector und Qdrant
- Konsistentes User-Bucketing (gleicher User = gleiche Variante)
- Graduelle Traffic-Splits (0-100%)
- Dual-Write für Daten-Synchronität
- Prometheus-Metriken für Experiment-Tracking

## Architektur

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Search Request                                    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     ABTestingRouter                                      │
│  - get_assignment(user_id) → Control/Treatment                          │
│  - Konsistentes Hashing (SHA256 % 100)                                  │
│  - Traffic Split: VECTOR_AB_TRAFFIC_SPLIT %                             │
└─────────────────────────────────────────────────────────────────────────┘
              │                                    │
              ▼                                    ▼
┌───────────────────────────┐      ┌───────────────────────────┐
│      Control (90%)        │      │     Treatment (10%)       │
│      ─────────────        │      │     ───────────────       │
│  Backend: pgvector        │      │  Backend: Qdrant          │
│  Embedding: E5-multilingual│      │  Embedding: E5 / Jina     │
│  Port: 5433 (PostgreSQL)  │      │  Port: 6333/6334          │
└───────────────────────────┘      └───────────────────────────┘
              │                                    │
              ▼                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      Metriken & Vergleich                               │
│  - Latenz (avg, p95, p99)                                               │
│  - Ergebnis-Qualität (avg_score)                                        │
│  - Error Rate                                                           │
└─────────────────────────────────────────────────────────────────────────┘
```

## Aktivierung (Schritt für Schritt)

### Phase 1: Qdrant Container starten

```bash
# Qdrant Container starten (falls noch nicht läuft)
docker-compose up -d qdrant

# Verifizieren
docker ps | grep qdrant
# Erwartete Ausgabe: ablage-qdrant ... Up ... healthy

# Health-Check
curl http://localhost:6333/readiness
# Erwartete Ausgabe: {"title":"qdrant - vectorass database","version":"1.7.4",...}
```

### Phase 2: Umgebungsvariablen konfigurieren

In `.env` oder `docker-compose.yml`:

```env
# ============================================================================
# Qdrant Vector Database
# ============================================================================
QDRANT_ENABLED=true
QDRANT_HOST=qdrant              # Container-Name in Docker-Netzwerk
QDRANT_HTTP_PORT=6333
QDRANT_GRPC_PORT=6334
QDRANT_PREFER_GRPC=true         # gRPC ist schneller

# Collection-Namen
QDRANT_COLLECTION_DOCUMENTS=ablage_documents
QDRANT_COLLECTION_CHUNKS=ablage_chunks

# HNSW Index (Standard-Werte für gute Balance)
QDRANT_HNSW_M=16                # Verbindungen pro Node
QDRANT_HNSW_EF_CONSTRUCT=128    # Build-Qualität

# ============================================================================
# A/B Testing Konfiguration
# ============================================================================
VECTOR_AB_TESTING_ENABLED=true
VECTOR_AB_TRAFFIC_SPLIT=10      # 10% Treatment (Qdrant)
VECTOR_AB_METRICS_ENABLED=true

# Backends
VECTOR_AB_CONTROL_BACKEND=pgvector
VECTOR_AB_TREATMENT_BACKEND=qdrant

# Embedding-Modelle (beide nutzen E5 für Fairness)
VECTOR_AB_CONTROL_EMBEDDING=intfloat/multilingual-e5-large
VECTOR_AB_TREATMENT_EMBEDDING=intfloat/multilingual-e5-large

# ============================================================================
# Dual-Write (Synchronisation)
# ============================================================================
VECTOR_DUAL_WRITE_ENABLED=true
VECTOR_DUAL_WRITE_ASYNC=true    # Non-blocking
VECTOR_MIGRATION_BATCH_SIZE=100
```

### Phase 3: Bestehende Embeddings zu Qdrant migrieren

```bash
# Migration über API starten
curl -X POST http://localhost:8000/api/v1/rag/admin/migration/start \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"

# Fortschritt prüfen
curl http://localhost:8000/api/v1/rag/admin/migration/status \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

Alternative: Python-Script

```python
import asyncio
from app.services.rag.vector_sync_service import get_vector_sync_service
from app.db.database import get_db_session

async def migrate():
    async with get_db_session() as db:
        sync_service = get_vector_sync_service()

        # Progress Callback
        async def on_progress(progress):
            print(f"Migration: {progress['progress_percent']}% "
                  f"({progress['processed_chunks']}/{progress['total_chunks']})")

        result = await sync_service.start_migration(
            db=db,
            progress_callback=on_progress
        )

        print(f"Migration abgeschlossen: {result}")

asyncio.run(migrate())
```

### Phase 4: Backend neu starten

```bash
# Backend-Container neu starten
docker-compose restart backend

# Logs prüfen
docker logs ablage-backend 2>&1 | grep -i "ab_testing\|qdrant"
# Erwartete Meldungen:
# ab_testing_router_initialized enabled=True traffic_split=10
# qdrant_service_initialized host=qdrant port=6333
```

### Phase 5: Verifizierung

```bash
# A/B Testing Status abrufen
curl http://localhost:8000/api/v1/rag/admin/ab-test/status \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

Erwartete Antwort:
```json
{
  "enabled": true,
  "traffic_split": 10,
  "control": {
    "backend": "pgvector",
    "embedding_model": "e5_multilingual"
  },
  "treatment": {
    "backend": "qdrant",
    "embedding_model": "e5_multilingual"
  },
  "metrics": {
    "control": {
      "total_requests": 0,
      "avg_latency_ms": 0,
      "errors": 0
    },
    "treatment": {
      "total_requests": 0,
      "avg_latency_ms": 0,
      "errors": 0
    }
  }
}
```

## Traffic-Split zur Laufzeit ändern

```bash
# Traffic-Split auf 20% erhöhen
curl -X POST http://localhost:8000/api/v1/rag/admin/ab-test/traffic-split \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"split": 20}'
```

## Metriken auswerten

### Via API

```bash
curl http://localhost:8000/api/v1/rag/admin/ab-test/metrics \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

### Via Prometheus (Grafana)

Metriken:
- `vector_search_latency_seconds{variant="control|treatment"}`
- `vector_search_total{variant="control|treatment",status="success|error"}`
- `vector_search_results_total{variant="control|treatment"}`

### Interpretation

| Metrik | Control (pgvector) | Treatment (Qdrant) | Fazit |
|--------|-------------------|-------------------|-------|
| avg_latency_ms | 45ms | 28ms | Qdrant 38% schneller |
| p99_latency_ms | 120ms | 62ms | Qdrant 48% bessere p99 |
| avg_score | 0.82 | 0.82 | Gleiche Qualität |
| error_rate | 0.1% | 0.05% | Beide stabil |

## Rollback bei Problemen

```bash
# A/B Testing deaktivieren (Sofort-Rollback)
curl -X POST http://localhost:8000/api/v1/rag/admin/ab-test/disable \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"

# Oder in .env:
VECTOR_AB_TESTING_ENABLED=false

# Und Backend neu starten
docker-compose restart backend
```

## Vollständiger Rollout (100% Qdrant)

Nach erfolgreicher Testphase:

```env
# .env
VECTOR_AB_TESTING_ENABLED=false
QDRANT_ENABLED=true

# pgvector weiterhin für Backup/Fallback nutzen
VECTOR_DUAL_WRITE_ENABLED=true
```

## Troubleshooting

### Qdrant nicht erreichbar

```bash
# Container-Status prüfen
docker ps | grep qdrant
docker logs ablage-qdrant

# Netzwerk-Konnektivität (aus Backend-Container)
docker exec ablage-backend curl -s http://qdrant:6333/readiness
```

### Migration hängt

```bash
# Migration abbrechen
curl -X POST http://localhost:8000/api/v1/rag/admin/migration/cancel \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"

# Status prüfen
curl http://localhost:8000/api/v1/rag/admin/migration/status \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

### Embeddings nicht synchron

```bash
# Sync-Status prüfen
curl http://localhost:8000/api/v1/rag/admin/sync/status \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"

# Erwartete Antwort zeigt points_count in Qdrant vs. Chunks in PostgreSQL
```

## Relevante Dateien

| Datei | Beschreibung |
|-------|-------------|
| `app/services/rag/ab_testing_router.py` | A/B Testing Router mit Bucketing |
| `app/services/rag/vector_sync_service.py` | Dual-Write und Migration |
| `app/services/vector/qdrant_service.py` | Qdrant Client-Wrapper |
| `app/core/config.py` | Konfigurationseinstellungen |
| `docker-compose.yml` | Qdrant Container-Definition |

## Konfigurationsreferenz

| Variable | Default | Beschreibung |
|----------|---------|-------------|
| `QDRANT_ENABLED` | `false` | Qdrant aktivieren |
| `QDRANT_HOST` | `localhost` | Qdrant Hostname |
| `QDRANT_HTTP_PORT` | `6333` | REST API Port |
| `QDRANT_GRPC_PORT` | `6334` | gRPC Port |
| `QDRANT_PREFER_GRPC` | `true` | gRPC bevorzugen |
| `VECTOR_AB_TESTING_ENABLED` | `false` | A/B Testing aktivieren |
| `VECTOR_AB_TRAFFIC_SPLIT` | `10` | % Traffic für Treatment |
| `VECTOR_AB_METRICS_ENABLED` | `true` | Metriken sammeln |
| `VECTOR_DUAL_WRITE_ENABLED` | `false` | Dual-Write aktivieren |
| `VECTOR_DUAL_WRITE_ASYNC` | `true` | Async Dual-Write |
| `VECTOR_MIGRATION_BATCH_SIZE` | `100` | Chunks pro Batch |

---

*Erstellt: 2025-12-17*
*Letzte Aktualisierung: 2025-12-17*
