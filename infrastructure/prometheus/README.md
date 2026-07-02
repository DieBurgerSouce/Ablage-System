# Prometheus Scrape-Token-Dateien

Prometheus scrapt einige Backend-/Service-Endpoints, die per Bearer-Token
abgesichert sind. Die Token-Dateien werden per `docker-compose` read-only ins
Prometheus-Image gemountet und sind **gitignored** (siehe `.gitignore`) — sie
werden also **nicht** eingecheckt und müssen lokal/prod vom Operator erzeugt
werden.

| Datei | Job(s) in `prometheus.yml` | Muss übereinstimmen mit |
|-------|-----------------------------|--------------------------|
| `metrics_scrape_token` | `ablage-backend`, `ablage-backup`, `ab-testing` | `METRICS_SCRAPE_TOKEN` in `.env` (Backend-Env) |
| `qdrant_metrics_token`  | `qdrant` | `QDRANT_API_KEY` in `.env` (Qdrant-Service) |

## Token-Dateien erzeugen

```bash
# Metrics-Scrape-Token (W1-022): Backend /internal-Endpoints
openssl rand -hex 32 > infrastructure/prometheus/metrics_scrape_token
# ... und denselben Wert als METRICS_SCRAPE_TOKEN in .env eintragen.

# Qdrant-Token (nur nötig, wenn QDRANT_API_KEY gesetzt ist)
printf '%s' "$QDRANT_API_KEY" > infrastructure/prometheus/qdrant_metrics_token
```

Wichtig:
- Die Datei darf **keinen** Zeilenumbruch enthalten, der nicht zum Token gehört
  (`openssl rand -hex 32` schreibt ein Newline; Prometheus trimmt Whitespace am
  Ende, das ist unkritisch — der Backend-Vergleich erfolgt gegen den getrimmten
  Wert). Wenn du unsicher bist: `printf '%s' "<token>" > datei`.
- **Dev-Verhalten:** Ist `METRICS_SCRAPE_TOKEN` in `.env` leer, erlaubt das
  Backend das Scraping ohne Token. Die Datei `metrics_scrape_token` muss aber
  trotzdem existieren, da der Bind-Mount sonst ein **Verzeichnis** anlegt und
  Prometheus die Datei nicht lesen kann. Ein beliebiger Platzhalter genügt in
  Dev.
- **Prod-Verhalten:** `METRICS_SCRAPE_TOKEN` (Backend) und
  `metrics_scrape_token` (Prometheus) **müssen identisch** sein, sonst
  antworten die Endpoints mit 403 (falscher Token) bzw. 503 (kein Token).
