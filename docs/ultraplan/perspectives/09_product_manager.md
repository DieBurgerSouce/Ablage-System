# 09 — Product Manager Perspektive

**Datum:** 2026-05-03
**Rolle:** Senior Product Manager (Outside-In)
**Frage:** Nicht "kann man es bauen?" sondern "warum bauen wir es ueberhaupt?"
**Scope:** Pilot Familienbetrieb Solingen (10 MA), Vergleich gegen lexoffice/sevDesk/d.velop

---

## 1-Sentence-Verdict

Ein Backend mit FAANG-Reife steckt im Kostuem einer Enterprise-Suite, die der Pilot-Kunde nie brauchen wird — wer 100 Sidebar-Items, 299 Routen und ein Privat-DMS samt Nachlassplanung serviert, hat das Produkt-Problem ("Eingangsrechnung in 2 Min") in einer Lawine von Features begraben.

---

## 2. Time-to-First-Value (TTFV)

**Geschaetzte TTFV bis zur ersten verarbeiteten Eingangsrechnung:** 35-90 Minuten (heute), Ziel-Soll: 5-10 Min.

**Code-Evidenz:**
- Onboarding existiert: `frontend/src/components/onboarding/CompanySetupWizard.tsx` mit 4 Schritten (Firmendetails, User-Einladung, Kontenrahmen, Zusammenfassung). Pragmatisch, aber nur localStorage (`ablage_onboarding_complete`) — kein Backend-Profile-Feld.
- Erforderliche Vorab-Einrichtung: Docker-Compose hochfahren, MinIO/Redis/PostgreSQL/OCR-Worker (~5-10 Min wenn Images bereits gepullt), 2FA-Setup, DATEV-Kontenrahmen-Auswahl, ggf. Lexware-Import.
- **Live-Walk Befund (`00j_LIVE_SYSTEM_REPORT.md` §4.2):** Backend war gar nicht hoch — kein User wuerde es ohne Admin-Begleitung schaffen.
- Vergleich: lexoffice = 5 Min Setup, voll cloud-managed. Wir haben *self-hosted on-premises* als Architektur-Constraint — daher ist TTFV strukturell hoeher. Trotzdem realistisch erreichbar: 10 Min, wenn Docker-Setup als One-Click-Installer geliefert wird.

**Pilot-Risiko:** Ohne Installer-Skript wird Bens Familienbetrieb am Tag 1 30+ Min nur Container-Debugging machen. Das ist **die** UX-Bedrohung.

---

## 3. Pilot-relevante vs irrelevante Routes (Mapping)

299 Routen. Pilot-Workflow: *Eingangsrechnung scannen -> OCR -> Buchen -> DATEV-Export -> Wiederfinden*.

| Bereich | Routen-Anzahl | Pilot-Relevanz | Begruendung |
|---------|---------------|----------------|-------------|
| Auth (login, forgot-password, reset, 2FA) | 4 | ESSENTIELL | Login-Funnel |
| Dashboard, Inbox, Search, Upload, Documents | ~10 | ESSENTIELL | Kern-Workflow |
| Banking (Kassenbuch, Skonto, Reconciliation) | ~7 | ESSENTIELL | Skonto-Versprechen |
| Mahnwesen | 7 | ESSENTIELL | Mehrwert-Versprechen |
| DATEV (Export, DATEVconnect) | 7 | ESSENTIELL | Steuerberater-Bridge |
| Lieferanten, Kunden | ~12 | ESSENTIELL | Hierarchische Ablage |
| Lexware Import | 4 | RELEVANT | Migration-Pfad |
| OCR-Suite, OCR-Review, OCR-Training | ~8 | NUR ADMIN | nicht End-User |
| **adhoc-reporting (3)** | 3 | NICHT RELEVANT | Custom Reports — Familienbetrieb braucht 2 fixe Reports, kein Builder |
| **streckengeschaeft (8)** | 8 | NICHT RELEVANT | Drop-Shipment ist USt-Spezialfall fuer wenige Branchen, Solingen Messer-Schmiede macht das nicht |
| **personal (4)** | 4 | NICHT RELEVANT | HR/Personalakten — kein Pilot-Versprechen |
| **privat.* (20)** | 20 | NICHT RELEVANT | Privates DMS (Immobilien, Fahrzeuge, Versicherungen, Nachlassplanung, Altersvorsorge) — **falsches Produkt** fuer Familienbetrieb |
| **admin.esg (7)** | 7 | NICHT RELEVANT | ESG-Reporting fuer 10-MA-Betrieb absurd |
| **holding (2)** | 2 | NICHT RELEVANT | Holding-Reconciliation = Konzern-Feature |
| **digital-twin, knowledge-graph, document-graph, agent-chat, chat, ki-pipeline, ml-dashboard, predictive, fraud, trust-dashboard** | ~12 | NICE-TO-HAVE | "wow"-Features, aber nicht Pilot-Erfolg-relevant |
| **portal (8)** | 8 | NICHT RELEVANT | Kunden-Portal = Phase 2, kein Pilot-Feature |
| **command-center, smart-dashboard, dashboard.ceo, executive, smart-search, spotlight, proactive-assistant** | ~7 | DUPLIKATE | Bereits 6 verschiedene "Dashboards" — Cognitive-Overload-Verdacht |
| **tax-package, ki-pipeline, ml-dashboard, recurring-invoices, contracts, vertraege, sendungen** | ~10 | OPTIONAL | Sekundaere Features |
| Workflow-Builder, BPMN, automation, approvals, prozesse | ~10 | NUR-ADMIN | Wenn ueberhaupt — Familienbetrieb baut keine Custom Workflows |

**Befund:** Schaetzungsweise **40-50 Routen** sind Pilot-relevant. **Die uebrigen ~250 verstecken**, nicht loeschen — sondern via Feature-Flags aus der Sidebar entfernen.

---

## 4. Cognitive Load

`Sidebar.tsx` enthaelt **108 SidebarLink-Eintraege** in einer 558-LOC-Datei. Submenus fuer Berichte/Finanzen/Admin existieren, aber das Top-Level ist schon ueberfrachtet (Dashboard, Command-Center, Smart Inbox, Proaktiver Assistent, Smart Search, CEO Dashboard, Smart Dashboard, Analyse, Vorhersagen, Digitaler Zwilling, KI-Assistent, Chat, E-Mail Import, Upload, Job Queue, Validierung, Dokumentgruppen, Auftragsketten, Dokumenten-Graph, Wissens-Graph, DATEV, DATEVconnect, E-Rechnungen ... — und das vor dem ersten Submenu).

**Azubi-Test (hypothetisch):** Wenn ein 17-jaehriger Azubi am ersten Tag eine Eingangsrechnung scannen soll — wo klickt er? Bei "Upload Wizard"? Bei "Smart Inbox"? Bei "Scanner"? Bei "scan"? Es gibt 4 Kandidaten. Das ist eine **Discovery-Falle**.

---

## 5. Hidden Features — was fuer den Familienbetrieb verschwinden muss

Nicht aus dem Backend loeschen — sondern via Tenant-Feature-Flag ausblenden. Kandidaten:

1. **Privat-DMS komplett (20 Routen, `features/privat/`)** — Nachlassplanung, Immobilien, Fahrzeuge, Altersvorsorge, Notfall-Cockpit. Das ist ein **eigenes Produkt** ("Ablage-Privat"), keine B2B-Pilot-Funktion. Sollte hinter Feature-Flag `enable_privat_module` und nur fuer User mit Rolle `privat_user`.
2. **Streckengeschaeft (8 Routen)** — Drop-Shipment + ZM-Meldung. Solinger Messer-Schmiede liefert direkt. Verstecken via `enable_drop_shipment_module`.
3. **ESG-Modul (7 Admin-Routen)** — CO2-Reporting, ESG-Goals, ESG-Suppliers. Fuer KMU mit 10 MA gesetzlich nicht relevant (CSRD-Schwellen >250 MA / 50M Umsatz).
4. **Adhoc-Reporting Builder (3 Routen)** — Familie braucht 2 fixe Reports (DATEV-Export, Offene Posten), keinen Drag-Drop-Report-Builder.
5. **RAG/Agent-Chat/KI-Pipeline/Knowledge-Graph/Digital-Twin/ML-Dashboard (~10 Routen)** — Beeindruckende Tech-Demos, aber fuer Pilot nicht sinnvoll. Wenn 0 Eingangsrechnungen im System sind, kann KI-Assistent nichts. Erst nach 6 Monaten Echtbetrieb wertvoll.

**Effekt:** Sidebar von 108 -> ~35 Eintraegen. Routes von 299 -> ~70 sichtbaren. Discovery-Falle entschaerft.

---

## 6. User-Personas

**Befund:** *Keine Persona-Dokumente im Repo gefunden* (`find -iname "*persona*"` -> nur DB-bezogene Treffer wie "personal_permissions"). Es gibt Rollen (`isAdmin`, `isEditor`, `privat_user`, `canViewMahnwesen`, `canViewOCRTraining`), aber **keine narrativ ausgearbeiteten Personas**.

**Implikation:** Das Produkt ist gebaut **ohne dokumentierten Ziel-User**. Daher die Feature-Inflation — jedes Feature ist legitim "fuer irgendwen", weil niemand definiert hat, fuer wen *nicht*. Klassisches Anti-Pattern.

**Empfehlung Phase 2:** 3 Personas verschriftlichen:
- "Prokurist Bernd, 52" (taegliche Buchhaltung, druckt gerne)
- "Azubi Lara, 17" (mobile-first, will scannen + tippen)
- "Steuerberater Schmidt" (will DATEV-Export + Audit-Trail)

Alle anderen Rollen (CEO-Dashboard-User, ML-Engineer, ESG-Officer) werden im Pilot **explizit ignoriert**.

---

## 7. Onboarding-Funnel & Drop-off

**Schritte (rekonstruiert aus Code):**

1. Docker-Compose hochfahren (Admin-Setup, kein User-Schritt) — **Drop-off-Risiko 80%** ohne Installer
2. Login-Page besuchen — funktioniert (Live-Walk verifiziert)
3. Login durchfuehren (per Email + Passwort) — ungetestet (Backend offline)
4. WelcomeModal erscheint (`localStorage.ablage_onboarding_complete` leer)
5. CompanySetupWizard (4 Schritte: Firma, User, Kontenrahmen, Done) — pragmatisch
6. Erstes Dokument hochladen — `/upload` Route oder Smart-Inbox oder Scanner
7. OCR-Verarbeitung warten — kein dokumentierter Progress
8. Validierung im Validation-Queue — Permission gated
9. DATEV-Export — eigene Route

**Drop-off-Hotspots:**
- Schritt 1 (Docker): jeder Nicht-IT-User scheitert
- Schritt 6 (4 Upload-Pfade): Discovery-Problem
- Schritt 7 (OCR-Wartezeit): kein Progress-Indicator-Audit durchgefuehrt — wenn fehlt, Pilot-User vermutet System haengt

---

## 8. Feature-Tiefe vs Breite

ANALYSIS sagt 4.8/5 Tiefe. FAANG sagt 7.5/10 Production-Readiness. Beide Recht (siehe Ground-Truth §5.3). Die brutale Wahrheit aus PM-Sicht:

**Wir haben 127 Features fuer einen Pilot-Kunden, der 12 davon braucht.**

Das ist nicht *Tiefe*, das ist **Breite-die-als-Tiefe-verkleidet-ist**. Echter Tiefen-Indikator: Wie reif ist *eine* Eingangsrechnungs-Verarbeitung? Antwort aus Audit: extrem reif (OCR + Self-Learning + Hash-Chain + DATEV-Mapping + Mahnwesen). Aber das ist **1 Workflow**. Drumherum 126 Features die niemand testet.

---

## 9. Killer-Feature-Wahl (mit Begruendung)

**DER EINE Grund fuer Wechsel von lexoffice: GoBD-Hash-Chain + On-Premises-Souveraenitaet**

Begruendung:
- lexoffice/sevDesk/DATEV-Online sind Cloud-only. Sensitive Belege (Loehne, IBAN-Listen, Kunden-Stammdaten) liegen in fremden Rechenzentren.
- DSGVO-Auftragsverarbeitungs-Vertraege sind formal — aber "die Daten sind hier im Haus" ist ein **emotional ueberzeugendes Argument** fuer Mittelstaendler ueber 50, die genau diese Kunden-Generation sind, die noch wechselt.
- GoBD-Hash-Chain (SHA-256 EventStore, Commit `0559fd15`) erzeugt **kryptographische Aenderungs-Beweise**, die SaaS-Konkurrenten nur als Versprechen liefern. Bei BFH-Pruefung ist das ein hartes Asset, kein Marketing.
- On-Premises + Hash-Chain ist eine *defensible position* (nicht nachbaubar in 6 Monaten von lexoffice, weil deren ganze Architektur SaaS ist).

**Gegen-Kandidaten verworfen:**
- *OCR-Qualitaet*: lexoffice hat auch OCR, gleichwertig fuer Standard-Rechnungen — kein Differentiator
- *Perpetual License*: Wirtschaftlich attraktiv, aber kein emotional Verkaufs-Argument (Geld ist rational, Sicherheit ist emotional)
- *Deutsche Sprachverarbeitung*: Wettbewerber sind ebenfalls deutsch
- *Feature-Vielfalt (127!)*: Ist eine **Schwaeche**, kein Feature

**Marketing-Slogan-Form:** "Ihre Belege bleiben in Solingen. Mit unfaelschbarem Beweis."

---

## 10. 5-Features-SOFORT-Deletion-Liste (fuer Pilot-Fokus)

Per Feature-Flag deaktivieren, **nicht** Code loeschen:

1. **Privat-DMS** (`features/privat/`, 20 Routen) — falsches Produkt fuer B2B-Pilot
2. **ESG-Modul** (`features/esg/`, 7 Admin-Routen) — gesetzlich nicht relevant
3. **Adhoc-Reporting-Builder** (`adhoc-reporting.*`, 3 Routen) — Overkill, durch 2 fixe Reports ersetzen
4. **Streckengeschaeft** (`features/drop-shipment/`, 8 Routen) — Branchen-Sonderfall, irrelevant fuer Solinger Schmiede
5. **Knowledge-Graph + Digital-Twin + Document-Graph + Agent-Chat + Chat + Predictive + Fraud + Trust-Dashboard + ML-Dashboard + KI-Pipeline** (~10 Routen) — bundeln als "Lab"-Bereich, ausgeblendet, **nach** Pilot reaktivierbar wenn Daten da sind

**Effekt auf Sidebar:** 108 -> 35-40 Eintraege. Auf User-Discovery: 4 Upload-Wege werden zu 1.

---

## 11. Pilot-Erfolgsmessung (Telemetrie)

**Code-Suche** `find frontend/src -name "*analytics*" -o -name "*telemetry*"`:
- Es gibt eine `features/analytics/` Route — aber das ist **Business-Analytics fuer den User** (Dokument-Volumen, Kostenanalyse), nicht Produkt-Telemetrie ueber den User.
- Grep nach `posthog|sentry|mixpanel|amplitude|gtag|matomo|plausible`: **0 echte Treffer im Frontend** (nur ein Sentry-Kommentar in `finanzen.tsx:9` "future: Sentry").
- Es gibt `/api/v1/errors`-Endpoint (self-rolled, Frontend-AUDIT §1) — fuer Errors, nicht fuer Funnel.

**Befund:** Es gibt **keine Produkt-Telemetrie**. Nach dem Pilot gibt es keinen Datenpunkt zu:
- Welche Routen werden tatsaechlich besucht?
- Wo brechen User ab?
- Wie lange dauert die erste Rechnung?
- Welche Features werden nie geoeffnet?

**Pilot-Blocker:** Ein Pilot ohne Telemetrie ist ein Pilot ohne Lernen. PostHog (DSGVO-konform self-hostable) oder Plausible einbauen. **Effort: 1-2 Tage.** **Wert: unbezahlbar fuer das naechste Pilot-Iteration.**

---

## 12. Top-3 Produkt-Staerken

1. **Killer-Feature steht solide:** GoBD-Hash-Chain + On-Premises ist ein *echter* Differentiator, kein Marketing. Backend-Reife stuetzt das (Audit `00b` und `00c`).
2. **Pilot-Workflow ist rein technisch da:** Eingangsrechnung -> OCR (Self-Learning, 4 Backends) -> Buchen (Skonto-Tracking, Mahnwesen) -> DATEV-Export — alle Bausteine existieren produktionsreif.
3. **Polish-Niveau wo es zaehlt:** Login, 404, Empty-States, deutsche UX (mit *einem* Umlaut-Bug), 2FA, Password-Reset — Pilot-Blocker substantiell adressiert (Frontend-Audit Note 8/10).

---

## 13. Top-5 Produkt-Schwaechen

1. **127 Features fuer 1 Pilot-Kunde** — Feature-Inflation ohne dokumentiertes "Nein". Kein PRD, keine Personas, keine Out-of-Scope-Liste.
2. **0 Telemetrie, 0 Funnel-Tracking** — Pilot ohne Lernen. Wir wissen nicht, was funktioniert.
3. **TTFV strukturell zu hoch** — kein One-Click-Installer, Docker-Compose-Knigge fuer den End-User. lexoffice 5 Min, wir 35-90 Min.
4. **Sidebar-Cognitive-Overload** — 108 Items, 6 Dashboards, 4 Upload-Wege. Azubi findet nichts ohne Anleitung.
5. **Onboarding lebt im localStorage** — Browser-Wechsel = neuer Onboarding-Flow. Kein Backend-Profile-Feld `onboarding_completed_at`.

---

## 14. Note: Produkt-Reife

**Note: 5/10**

Begruendung: Engineering-Reife ist Top (Backend 8-9, Frontend 8). **Produkt-Reife ist Mitte.** Es fehlt die produktstrategische Disziplin: kein PRD, keine Personas, keine Out-of-Scope-Liste, keine Telemetrie, keine Pilot-Erfolgsmetriken, keine Feature-Flags fuer Tenant-spezifische Sichtbarkeit. Die *Maschine* ist fertig, das *Produkt* nicht. Bei einem Pilot ohne diese Disziplin lernen wir am Ende: "es funktioniert", aber nicht *was* funktioniert oder *wer* es nutzt.

---

## 15. Drei PM-Empfehlungen fuer Pilot-Vorbereitung (4 Wochen)

**Empfehlung 1 — Tenant-Feature-Flags + Familienbetrieb-Profil (3-4 Tage):**
Eine Pilot-Konfiguration `tenant_profile=familienbetrieb_klein`, die per Default deaktiviert: privat.\*, streckengeschaeft.\*, esg.\*, adhoc-reporting.\*, knowledge-graph, digital-twin, agent-chat, chat, ml-dashboard, ki-pipeline, predictive, fraud, trust-dashboard, holding, personal. Sidebar von 108 auf ~35. Routes von 299 auf ~70 sichtbar. Code bleibt.

**Empfehlung 2 — Telemetrie + Pilot-KPIs (2 Tage):**
PostHog selbst-gehostet (DSGVO-konform). Tracken: Login-Erfolg-Rate, TTFV (Login -> erste verarbeitete Rechnung), Routen-Heatmap (welche 12 von 299 werden wirklich besucht?), Drop-off-Punkte. Pilot-KPI-Dashboard mit Bens 4 Versprechen: <2 Min/Rechnung, <10 Sek-Suche, 0 verpasste Skonto, <15 Min DATEV. Live-Messung waehrend Pilot.

**Empfehlung 3 — One-Click-Setup-Skript + Personas-PRD (3 Tage):**
Bash-/PowerShell-Installer fuer Familienbetrieb (Docker-Compose-Up + Health-Check + Initial-Admin-User + 2FA-Setup-Link in einem). TTFV von 35-90 Min auf 10 Min. Parallel: 3-Personas-PRD (Prokurist, Azubi, Steuerberater) als Anchor fuer alle weiteren Feature-Entscheidungen — und als Filter fuer "wuerde Bernd das brauchen?" Nein-Frage fuer alle 50+ Nicht-Pilot-Features.

---

**Schlusswort:** Die System-Frage ist nicht *"Sind wir bereit?"* — wir sind technisch fast bereit. Die System-Frage ist: *"Wissen wir, wofuer wir bereit sind?"* — und da fehlt PM-Disziplin, nicht Code.
