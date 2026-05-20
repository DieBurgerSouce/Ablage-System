# API v1 Endpoints

> **Letzte Aktualisierung**: 2026-01-27
> **Version**: 1.0

---

## Übersicht

Dieses Verzeichnis enthält alle FastAPI Router für die v1 API. Alle Endpunkte sind unter `/api/v1/` erreichbar und erfordern JWT-Authentifizierung (sofern nicht anders angegeben).

**Basis-URL**: `/api/v1`
**Authentifizierung**: JWT Bearer Token (httpOnly Cookie)
**Rate Limiting**: 100 Requests/Minute (Standard)

---

## Router-Kategorien

### Dokument-Management

| Router | Pfad | Beschreibung |
|--------|------|--------------|
| `documents.py` | `/documents` | CRUD, Upload, Download, OCR-Trigger |
| `document_chains.py` | `/document-chains` | Auftragsketten-Tracking |
| `document_tasks.py` | `/document-tasks` | Dokument-Aufgaben |
| `document_templates.py` | `/document-templates` | Dokumentvorlagen |
| `versions.py` | `/versions` | Versionsverwaltung |
| `trash.py` | `/trash` | Papierkorb-Verwaltung |
| `sharing.py` | `/sharing` | Dokument-Freigaben |
| `comments.py` | `/comments` | Dokument-Kommentare |
| `favorites.py` | `/favorites` | Favoriten-Verwaltung |
| `compare.py` | `/compare` | Dokumentvergleich |

### OCR & KI

| Router | Pfad | Beschreibung |
|--------|------|--------------|
| `ocr_learning.py` | `/ocr-learning` | OCR Self-Learning, A/B Tests |
| `ai.py` | `/ai` | KI-Finanzassistent |
| `ai_autonomy.py` | `/ai/autonomy` | Autonome KI-Aktionen |
| `ml.py` | `/ml` | Machine Learning APIs |
| `rag.py` | `/rag` | Retrieval-Augmented Generation |
| `knowledge.py` | `/knowledge` | Wissensbasis |

### Business Entities & Lexware

| Router | Pfad | Beschreibung |
|--------|------|--------------|
| `entities.py` | `/entities` | Geschäftspartner CRUD |
| `lexware.py` | `/lexware` | Lexware Import |
| `business_contacts.py` | `/contacts` | Kontaktpersonen |
| `streckengeschaeft.py` | `/streckengeschaeft` | Streckengeschäft |

### Rechnungswesen

| Router | Pfad | Beschreibung |
|--------|------|--------------|
| `invoices.py` | `/invoices` | Rechnungen, Skonto, Mahnung |
| `accounting.py` | `/accounting` | Buchhaltung |
| `datev.py` | `/datev` | DATEV Export |
| `einvoice.py` | `/einvoice` | E-Rechnung (XRechnung, ZUGFeRD) |
| `expenses.py` | `/expenses` | Ausgaben |
| `budgets.py` | `/budgets` | Budgets |

### Banking & Finanzen

| Router | Pfad | Beschreibung |
|--------|------|--------------|
| `banking_fints.py` | `/banking` | FinTS Banking |
| `transactions.py` | `/transactions` | Transaktionen |
| `cash.py` | `/cash` | Kassenbuch |
| `payment_behavior.py` | `/payment-behavior` | Zahlungsverhalten |
| `predictive_cashflow.py` | `/cashflow` | Cash Flow Prognose |
| `finance.py` | `/finance` | Finanzübersicht |

### Fraud & Risk

| Router | Pfad | Beschreibung |
|--------|------|--------------|
| `fraud_detection.py` | `/fraud` | Betrugserkennung |
| `risk_intelligence.py` | `/risk` | Risiko-Bewertung |
| `supplier_ranking.py` | `/suppliers/ranking` | Lieferanten-Ranking |

### Workflows & Approvals

| Router | Pfad | Beschreibung |
|--------|------|--------------|
| `workflows.py` | `/workflows` | Workflow-Definitionen |
| `approvals.py` | `/approvals` | Genehmigungen |
| `bpmn.py` | `/bpmn` | BPMN-Workflows |
| `delegations.py` | `/delegations` | Delegationen |
| `smart_escalation.py` | `/escalation` | Smart Eskalation |

### Compliance & GDPR

| Router | Pfad | Beschreibung |
|--------|------|--------------|
| `gdpr.py` | `/gdpr` | DSGVO-Rechte |
| `compliance.py` | `/compliance` | Compliance-Checks |
| `dlp.py` | `/dlp` | Data Loss Prevention |
| `vault.py` | `/vault` | Tresor (sichere Dokumente) |

### Administration

| Router | Pfad | Beschreibung |
|--------|------|--------------|
| `companies.py` | `/companies` | Firmen-Verwaltung |
| `groups.py` | `/groups` | Gruppen/Rollen |
| `teams.py` | `/teams` | Teams |
| `settings.py` | `/settings` | Einstellungen |
| `subscriptions.py` | `/subscriptions` | Abonnements |
| `tenant_rate_limits.py` | `/rate-limits` | Rate Limits |
| `mfa.py` | `/mfa` | Multi-Faktor-Auth |
| `security.py` | `/security` | Sicherheit |

### Holding & Multi-Company

| Router | Pfad | Beschreibung |
|--------|------|--------------|
| `holding.py` | `/holding` | Holding-Dashboard |

### Import & Export

| Router | Pfad | Beschreibung |
|--------|------|--------------|
| `imports.py` | `/imports` | Email/Folder Import |
| `exports.py` | `/exports` | Dokument-Export |
| `scheduled_exports.py` | `/scheduled-exports` | Geplante Exports |
| `backup.py` | `/backup` | Backup-Verwaltung |

### Integrationen

| Router | Pfad | Beschreibung |
|--------|------|--------------|
| `slack.py` | `/slack` | Slack Integration |
| `shipments.py` | `/shipments` | Sendungsverfolgung |
| `webhooks.py` | `/webhooks` | Webhooks |

### Benachrichtigungen

| Router | Pfad | Beschreibung |
|--------|------|--------------|
| `notifications.py` | `/notifications` | Benachrichtigungen |
| `notification_rules.py` | `/notification-rules` | Benachrichtigungsregeln |
| `push_notifications.py` | `/push` | Push-Benachrichtigungen |

### Suche & Analytics

| Router | Pfad | Beschreibung |
|--------|------|--------------|
| `search.py` | `/search` | Dokumentensuche |
| `unified_search.py` | `/unified-search` | Unified Search |
| `log_analytics.py` | `/logs` | Log-Analyse |
| `activity.py` | `/activity` | Aktivitäts-Feed |
| `activity_timeline.py` | `/timeline` | Zeitleiste |

### Dashboards & Reports

| Router | Pfad | Beschreibung |
|--------|------|--------------|
| `dashboard.py` | `/dashboard` | Haupt-Dashboard |
| `dashboards.py` | `/dashboards` | Custom Dashboards |
| `reports.py` | `/reports` | Report-Generierung |
| `proactive_insights.py` | `/insights` | Proaktive Insights |

### System & Monitoring

| Router | Pfad | Beschreibung |
|--------|------|--------------|
| `health.py` | `/health` | Health Check (public) |
| `readiness.py` | `/readiness` | Readiness Check |
| `metrics.py` | `/metrics` | Prometheus Metrics |
| `profiling.py` | `/profiling` | Profiling |
| `hardware.py` | `/hardware` | Hardware-Status (GPU) |
| `hygiene.py` | `/hygiene` | System-Hygiene |

### Privat-Modul

| Router | Pfad | Beschreibung |
|--------|------|--------------|
| `privat.py` | `/privat` | Privat-Finanzen |
| `privat_analytics.py` | `/privat/analytics` | Privat-Analysen |
| `personal.py` | `/personal` | Persönliche Einstellungen |

### Weitere

| Router | Pfad | Beschreibung |
|--------|------|--------------|
| `calendar.py` | `/calendar` | Kalender |
| `contracts.py` | `/contracts` | Verträge |
| `tasks.py` | `/tasks` | Aufgaben |
| `training.py` | `/training` | Training-Daten |
| `validation.py` | `/validation` | Validierung |
| `help.py` | `/help` | Hilfe-System |
| `magic_buttons.py` | `/magic` | Magic Buttons |
| `oneclick.py` | `/oneclick` | One-Click Actions |
| `agents.py` | `/agents` | Agent-Status |
| `batch_jobs.py` | `/batch` | Batch-Jobs |
| `orchestration.py` | `/orchestration` | Cross-Module Events |
| `routing.py` | `/routing` | OCR Routing |
| `saved_filters.py` | `/filters` | Gespeicherte Filter |
| `predictive_actions.py` | `/predictive` | Predictive Actions |
| `tax_advisor.py` | `/tax-advisor` | Steuerberater |
| `tax_advisor_packages.py` | `/tax-packages` | Steuerberater-Pakete |
| `websocket.py` | `/ws` | WebSocket |

---

## Öffentliche Endpunkte (keine Auth)

- `GET /api/v1/health` - Health Check
- `GET /api/v1/readiness` - Readiness Check
- `GET /api/v1/metrics` - Prometheus Metrics

---

## Router-Pattern

Alle Router folgen dem gleichen Pattern:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.db.models import User

router = APIRouter(prefix="/feature", tags=["Feature"])

@router.get("/")
async def list_items(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Listet alle Items auf."""
    ...
```

---

## Fehlerbehandlung

Alle API-Fehler folgen dem standardisierten Format:

```json
{
  "error_code": "DOC_NOT_FOUND",
  "message": "Dokument nicht gefunden",
  "details": {
    "document_id": "..."
  }
}
```

Siehe `.claude/Docs/API/ErrorCatalog.md` für alle Fehler-Codes.

---

## Sicherheit

1. **JWT Auth**: Alle Endpunkte (außer public) erfordern gültiges JWT
2. **RBAC**: Rollenbasierte Zugriffssteuerung
3. **Multi-Tenant**: Company-Isolation via RLS
4. **Rate Limiting**: Per-Endpoint konfigurierbar
5. **Input Validation**: Pydantic Schemas für alle Requests
