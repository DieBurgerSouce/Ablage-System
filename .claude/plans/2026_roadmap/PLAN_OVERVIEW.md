# Plan: Feature Roadmap 2026

> **Status**: In Planung
> **Erstellt**: 2026-01-02
> **Geschaetzter Gesamtaufwand**: 26-34 Wochen
> **Anzahl Features**: 10
> **Basierend auf**: Interview mit Projektinhaber (01.01.2026)

---

## Executive Summary

Das Ablage-System wird 2026 zu einer vollstaendigen Enterprise-Plattform ausgebaut. Der Fokus liegt auf **Multi-Firma Architektur** als Fundament, **GoBD-Compliance** fuer rechtliche Absicherung, und **intelligenter Automatisierung** fuer maximale Zeitersparnis. Die Odoo-Integration ersetzt langfristig Lexware als ERP-System.

**Kernphilosophie:**
> "Zeitersparnis durch KI-Autonomie - aber nur wenn es todsicher und compliant funktioniert"

---

## Feature-Uebersicht

| # | Feature | Prioritaet | Aufwand | Status | Datei |
|---|---------|------------|---------|--------|-------|
| 01 | Multi-Firma Architektur | P1 | 4-6W | Geplant | [FEATURE_01](./FEATURE_01_multi_company.md) |
| 02 | GoBD-Zertifizierung | P1 | 3-4W | Geplant | [FEATURE_02](./FEATURE_02_gobd_compliance.md) |
| 03 | Intelligentes Benachrichtigungssystem | P1 | 3-4W | Geplant | [FEATURE_03](./FEATURE_03_notifications.md) |
| 04 | Odoo-Integration | P2 | 4-5W | Geplant | [FEATURE_04](./FEATURE_04_odoo_integration.md) |
| 05 | Dashboard & KPIs | P2 | 3-4W | Geplant | [FEATURE_05](./FEATURE_05_dashboard_kpis.md) |
| 06 | E-Mail & Ordner-Import | P2 | 2-3W | Geplant | [FEATURE_06](./FEATURE_06_email_import.md) |
| 07 | KI-Autonomie erweitern | P2 | 3-4W | Geplant | [FEATURE_07](./FEATURE_07_ki_autonomie.md) |
| 08 | Report-Builder | P3 | 3-4W | Geplant | [FEATURE_08](./FEATURE_08_report_builder.md) |
| 09 | Workflow-Automation | P3 | 5-6W | Geplant | [FEATURE_09](./FEATURE_09_workflow_automation.md) |
| 10 | Mobile PWA | P3 | 2-3W | Geplant | [FEATURE_10](./FEATURE_10_mobile_pwa.md) |

---

## Abhaengigkeiten

```
┌─────────────────────────────────────────────────────────────────┐
│                    ABHAENGIGKEITS-GRAPH                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌───────────────────┐                                          │
│  │ 01: Multi-Firma   │ ◄─── FUNDAMENT FUER ALLES                │
│  │     (P1)          │                                          │
│  └────────┬──────────┘                                          │
│           │                                                     │
│     ┌─────┴─────┬─────────────────┐                             │
│     │           │                 │                             │
│     ▼           ▼                 ▼                             │
│  ┌──────┐   ┌──────┐         ┌──────────┐                       │
│  │ 02:  │   │ 03:  │         │ 04: Odoo │                       │
│  │ GoBD │   │Notif.│         │  (P2)    │                       │
│  │ (P1) │   │ (P1) │         └────┬─────┘                       │
│  └──┬───┘   └──┬───┘              │                             │
│     │          │                  │                             │
│     │          ▼                  ▼                             │
│     │     ┌──────────┐      ┌──────────┐                        │
│     │     │ 05: Dash │      │ 06: Mail │                        │
│     │     │  (P2)    │      │  Import  │                        │
│     │     └────┬─────┘      │  (P2)    │                        │
│     │          │            └──────────┘                        │
│     │          │                                                │
│     │          ▼                                                │
│     │     ┌──────────┐      ┌──────────┐                        │
│     └────►│ 08: Repo │      │ 07: KI   │ ◄── Unabhaengig        │
│           │ Builder  │      │ Autonomie│                        │
│           │  (P3)    │      │  (P2)    │                        │
│           └──────────┘      └──────────┘                        │
│                                                                 │
│                ┌──────────┐      ┌──────────┐                   │
│                │ 09: Work │      │ 10: PWA  │                   │
│                │ flows    │      │  (P3)    │                   │
│                │  (P3)    │      └──────────┘                   │
│                └──────────┘                                     │
│                     ▲                                           │
│                     │                                           │
│              Benoetigt: 01, 03, 05                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Kritischer Pfad

1. **Feature 01** (Multi-Firma) muss zuerst fertig sein
2. **Features 02, 03, 04** koennen parallel starten nach Feature 01
3. **Features 05, 06** koennen parallel zu Feature 04 laufen
4. **Features 08, 09** benoetigen Dashboard-Basis
5. **Features 07, 10** sind weitgehend unabhaengig

---

## Zeitplan

### Q1 2026: Foundation (Wochen 1-12)

| Woche | Feature | Meilenstein |
|-------|---------|-------------|
| 1-2 | 01: Multi-Firma | Architektur-Design finalisiert |
| 3-6 | 01: Multi-Firma | Implementation abgeschlossen |
| 3-4 | 02: GoBD-Basis | Anforderungen dokumentiert |
| 5-8 | 02: GoBD-Basis | Signatur + Aufbewahrung implementiert |
| 7-10 | 03: Notifications | Core-System live |
| 10-12 | Buffer | Bugfixes, Stabilisierung |

### Q2 2026: Core Features (Wochen 13-24)

| Woche | Feature | Meilenstein |
|-------|---------|-------------|
| 13-17 | 04: Odoo-Integration | Bidirektionale Sync funktional |
| 14-17 | 05: Dashboard | Widget-System + KPIs live |
| 18-20 | 06: E-Mail Import | IMAP + Ordner-Watcher aktiv |
| 18-21 | 07: KI-Autonomie | Confidence-basierte Entscheidungen |
| 22-24 | Buffer | Integration, Testing |

### Q3-Q4 2026: Polish & Expansion (Wochen 25-52)

| Woche | Feature | Meilenstein |
|-------|---------|-------------|
| 25-28 | 08: Report-Builder | Templates + Custom Reports |
| 29-34 | 09: Workflow-Automation | Regel-Engine + Visueller Editor |
| 35-37 | 10: Mobile PWA | Foto-Upload + Push aktiv |
| 38-42 | GoBD-Zertifizierung | Antrag eingereicht |
| 43-52 | Stabilisierung | Performance, Security, UX Polish |

---

## Risiken & Mitigationen

| Risiko | Wahrscheinlichkeit | Impact | Mitigation |
|--------|-------------------|--------|------------|
| Multi-Firma Architektur komplexer als gedacht | Mittel | Hoch | Fruehzeitige Prototypen, iterative Entwicklung |
| Odoo API aendert sich | Niedrig | Mittel | Abstraktionsschicht, Version-Pinning |
| GoBD-Zertifizierung scheitert | Niedrig | Hoch | Fruehzeitig Pruefstelle konsultieren |
| GPU-Ressourcen bei KI-Features | Mittel | Mittel | Fallback auf CPU, Batching optimieren |
| Scope Creep bei Workflow-Automation | Hoch | Mittel | MVP-Ansatz, klare Feature-Grenzen |

---

## Erfolgskriterien

### Quantitative Ziele

| Metrik | Ziel | Messung |
|--------|------|---------|
| Zeitersparnis pro Dokument | -50% | Vorher/Nachher Vergleich |
| KI-Autonomie Rate | >80% automatisch | Audit-Log Analyse |
| System Uptime | >99.5% | Prometheus Monitoring |
| API Response Time | <200ms (P95) | Grafana Dashboard |
| User Adoption | 100% der Mitarbeiter | Login-Statistik |

### Qualitative Ziele

1. [ ] GoBD-Zertifizierung erfolgreich beantragt
2. [ ] Beide Firmen nutzen Multi-Tenant Architektur
3. [ ] Odoo ersetzt Lexware fuer Firma 1
4. [ ] Mobile Zugriff fuer Geschaeftsfuehrung
5. [ ] Vollstaendige Audit-Trail fuer alle Dokumente

---

## Nicht-Ziele (Explizit ausgeschlossen)

- Dokumenten-Erstellung (bleibt in Lexware/Odoo)
- Plugin-Marketplace (zu frueh)
- Native Mobile App (PWA reicht)
- Internationale Expansion (Deutschland-First)
- AI-basierte Buchhaltung (Compliance-Risiko)

---

## Team & Ressourcen

### Benoetigte Rollen

| Rolle | Anteil | Features |
|-------|--------|----------|
| Backend Developer | 60% | Alle |
| Frontend Developer | 30% | 05, 09, 10 |
| DevOps Engineer | 10% | 01, 02, 04 |

### Hardware-Anforderungen

| Ressource | Aktuell | Benoetigt |
|-----------|---------|-----------|
| GPU (VRAM) | 16GB RTX 4080 | Ausreichend |
| Storage | 2TB | 4TB (Archivierung) |
| RAM | 64GB | Ausreichend |

---

## Review-Zyklen

- **Woechentlich**: Stand-Up, Blocker-Clearing
- **Alle 2 Wochen**: Sprint Review, Demo
- **Monatlich**: Roadmap Review, Prioritaeten-Anpassung
- **Quartal**: Stakeholder Update, Budget Review

---

## Dokumentation

| Dokument | Pfad | Aktualisierung |
|----------|------|----------------|
| Architektur | `.claude/Docs/ARCHITECTURE.md` | Bei Major Changes |
| API Referenz | `/docs` (Swagger UI) | Automatisch |
| User Guide | `.claude/Docs/USER_GUIDE.md` | Pro Feature |
| Runbooks | `.claude/Docs/Operations/` | Pro Deployment |

---

*Erstellt: 2026-01-02*
*Basierend auf: Interview-Session mit Projektinhaber*
*Naechste Review: 2026-01-15*
