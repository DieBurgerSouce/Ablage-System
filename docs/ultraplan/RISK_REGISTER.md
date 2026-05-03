# Risk Register

**Methodik:** Top-20-Risiken (technisch, geschäftlich, persönlich), sortiert nach Wahrscheinlichkeit × Impact. Pro Risiko: Eintrittswahrscheinlichkeit, Impact, Mitigation, Owner, Trigger-Event, Quelle.

**Skala:**

- Wahrscheinlichkeit (P): Low/Med/High
- Impact (I): Low/Med/High
- Score: P × I (Sortier-Kriterium)

**Owner:** Ben (Solo-Founder) für alle, sofern nicht anders vermerkt.

---

## Tier 1: Kritische Risiken (High×High = Score 9)

### R01 — Pilot-Reputations-Schaden bei Familienbetrieb-Crash

**P:** High × **I:** High = **9**

**Beschreibung:** Beim Pilot-Tag fällt Backend aus, Prokurist sieht 502er, ruft Familie an, Vertrauen verloren. Live-Walk hat bewiesen: Backend war offline, niemand wusste es. Plus 56 Silent-Catches an Compliance-Pfaden.

**Trigger-Event:** Backend-Container-Crash + ausbleibende Notification

**Mitigation:**

- Sprint 0: Slack-Webhook (G01) + Backend-Auto-Start (G05) + Sentry-DSN (G10)
- Sprint 1: Pilot-Workflow E2E-Test mit SLA-Asserts (G09)
- Sprint 5: Daily-Check-in-Plan + Hot-Fix-Prozess &lt;2h MTTR

**Quelle:** DevOps-Perspektive 5, Live-Walk 00j, Prokurist 1

---

### R02 — Externer Pentester findet Pilot-Blocker in &lt;1 Tag

**P:** High × **I:** High = **9**

**Beschreibung:** 3 Security-Pilot-Blocker (python-jose CVE, JWT-im-Body, CSP unsafe-inline) sind durch Standard-Pentester-Tooling sofort findbar. Bei Pilot-Kunden mit Steuerberater-Daten = sofortige Vertrauenskrise.

**Trigger-Event:** Pilot-Kunde verlangt Pentest-Bericht oder -Bestätigung, externer Pentester wird beauftragt

**Mitigation:**

- Sprint 0: G02 (jose), G03 (JWT-Cookie), G07 (Rate-Limit) — alle 2 Tage
- Sprint 2: G16 (CSP), G24 (CI-Audit-Tooling)
- Monat 5: Externer Pentest beauftragen NACH allen Sprint-0-2-Fixes

**Quelle:** Security-Audit 00h, Security-Perspektive 6

---

### R03 — Bus-Faktor-1: Ben wird krank/unavailable

**P:** Med × **I:** High = **6**

**Beschreibung:** 797 Services, 4 God-Objects &gt;60KB, kein Hire #2. Bei 6 Wochen Krankheit: Pilot-Kunde ohne Support, DATEV-Antrag stoppt, Code-Wartung stockt. Investor-Perspektive 11 nennt es Top-Risiko.

**Trigger-Event:** Krankheit, persönliche Krise, Burnout

**Mitigation:**

- Monat 9-12: Onboarding-Doc für Hire #2 (G51)
- Monat 12: Hire #2 bei 3+ zahlenden Kunden
- Sofort: Code-Doku-Drift-Audit (G59) + Bus-Faktor-Doku (selbst wenn nur Ben sie schreibt — wird klar wo Wissens-Inseln sind)

**Quelle:** Investor 11, Founder 10, GROUND_TRUTH §3.5

---

### R04 — DATEV-Zertifizierung dauert deutlich länger als 6 Monate

**P:** High × **I:** Med = **6**

**Beschreibung:** DATEV-Zertifizierung ist 6-12 Monate Aufwand. Compliance-Audit zeigt: DATEV-Belegbilder nicht produktiv, KOSIT-Validator fehlt, Schnittstellen-Antrag nicht eingereicht. Ohne DATEV: 80% Steuerberater-Markt unzugänglich.

**Trigger-Event:** Antrag wird abgelehnt oder Rückmeldung dauert &gt;9 Monate

**Mitigation:**

- Sprint 2: KOSIT-Validator integrieren (G18)
- Sprint 3: DATEV-Belegbilder-Upload produktiv (G34)
- Monat 6: Antrag JETZT einreichen, NICHT erst nach allen Fixes
- Plan-B: Lexware/sevDesk als Brücken-Integration (auch ohne DATEV-Zertifizierung)

**Quelle:** Compliance 7, 00i

---

### R05 — Multi-Tenant-Refactor blockiert Markt-Eintritt

**P:** Med × **I:** High = **6**

**Beschreibung:** Wenn Single-Tenant-pro-Instanz nicht akzeptabel ist (manche Kunden wollen SaaS), brauchen wir 2-4 Monate Multi-Tenant-Hardening. 13 Tables ohne `company_id`, 200+ manuelle Filter, kein zentraler Auth-Decorator.

**Trigger-Event:** Erster Kunde verlangt Cloud-Hosting bei Ben statt On-Prem

**Mitigation:**

- Sprint 8: Architektur-Decision dokumentieren (G37)
- Falls Single-Tenant-on-Prem: Decision halten, klar kommunizieren
- Falls Multi-Tenant nötig: Sprint M5 mit 8 Wochen einplanen
- ICP-Reframe (Founder 10): Family-Office-Light als On-Prem-only-Pivot ist legitim

**Quelle:** Backend 4, DB 00c, Sec 00h, Founder 10

---

## Tier 2: Hohe Risiken (Score 4-6)

### R06 — RTX 4080 Server stirbt → Pilot-Kunde offline

**P:** Low × **I:** High = **3**

**Beschreibung:** Single-Server-Single-GPU-Architektur. Hardware-Ausfall = Totalausfall. Kein Failover. RTO im DR_RUNBOOK.md nicht spezifiziert.

**Trigger-Event:** GPU-Burnout, Mainboard-Ausfall, RAM-Defekt

**Mitigation:**

- Sprint 0: Backup-Restore-Test bestätigen (G08)
- Monat 6: DR-RTO/RPO-SLA dokumentieren (G55)
- Bei 3+ Kunden: Cold-Standby-Server kaufen (\~3000€)
- Pilot-Vertrag: Klausel "RTO 4h, RPO 24h" — ehrlich kommunizieren

**Quelle:** DevOps 5, Infrastructure 00f

---

### R07 — Familienbetrieb-Pilot scheitert sichtbar im Bekanntenkreis

**P:** Med × **I:** Med = **4**

**Beschreibung:** Solingen ist klein, Bens Familie hat Netzwerk. Wenn Pilot scheitert, ist die Story in Bens lokalen Geschäftskreisen. Erste 5-10 Akquise-Gespräche im Bergisches Land sind dann blockiert.

**Trigger-Event:** Pilot-Workflow ungenutzt nach 4 Wochen, Prokurist nutzt Lexware weiter

**Mitigation:**

- Sprint 0-2: Pilot-Hardening absolut ernst nehmen
- Sprint 5: Daily-Check-in mit Pilot-Team
- Falls Pilot stockt: 1-2 Wochen länger Pilot-Phase, NICHT abbrechen
- Founder-Perspektive: ICP-Reframe vor Markt-Pitch (G58)

**Quelle:** Founder 10, Prokurist 1

---

### R08 — Code-Wachstum 4x schlägt um in Wartungs-Hölle

**P:** Med × **I:** Med = **4**

**Beschreibung:** Tempo Dez 2025 → Mai 2026: 210→797 Services, 93→299 Routes, 70→227 Migrations. Kein Refactor-Sprint. Bei nochmaliger Verdopplung wird God-Object-Count + Test-Coverage-Lücke unhaltbar.

**Trigger-Event:** Bug-Fix-Latenz steigt über 3 Tage, Pull-Request-Reviews schlagen fehl an Datei-Größe

**Mitigation:**

- Sprint 0: Konsolidierungs-Bias — keine neuen Features
- Monat 4: God-Object-Refactoring (G41-G45)
- Monat 9: Test-Coverage als CI-Gate (G60)
- Strikte Regel: Service-File &gt;30KB → automatischer Refactor-Ticket

**Quelle:** GROUND_TRUTH §3.1, Backend 4, API 00d

---

### R09 — GPT-5 / Cloud-LLMs machen lokale OCR überflüssig

**P:** Med × **I:** Med = **4**

**Beschreibung:** Bens USP "lokale OCR + GDPR-on-prem" konkurriert mit GPT-5/Claude/Gemini Cloud-Vision-APIs. Wenn Kunden bereit werden, Cloud zu nutzen (regulatorisch entspannt), erodiert der Differentiator.

**Trigger-Event:** EU-AI-Act erlaubt klar Cloud-OCR für GoBD-Daten, GPT-5 erreicht 99% Genauigkeit auf deutschen Belegen

**Mitigation:**

- Founder-Perspektive: Familie-Office-Light Pivot (G58, G61) reduziert OCR-Abhängigkeit
- Markt-Kommunikation: NICHT über OCR-Genauigkeit verkaufen (DataSci 8 sagt: Accuracy nicht gemessen), sondern über GoBD-Hash-Chain + Workflows
- Roadmap: RAG-Stack (Qwen3 lokal) als zweites Bein etablieren

**Quelle:** GROUND_TRUTH §3.4, DataSci 8, Founder 10

---

### R10 — KassenSichV/TSE-Anforderung trifft den Pilot

**P:** Low × **I:** High = **3**

**Beschreibung:** §146a AO + KassenSichV verlangt zertifizierte TSE für Bargeld-Endkundenumsätze. Wenn Pilot-Kunde ein POS-System integriert, oder wenn Auslegung sich ändert, droht Bußgeld bis 25.000€/Kasse + Hinzuschätzung.

**Trigger-Event:** Steuerberater des Pilot-Kunden meldet TSE-Bedarf, Außenprüfung beim Pilot-Kunden

**Mitigation:**

- Sprint 2: Steuerberater + Anwalt-Klärung (G35) — schriftlich!
- Bei Zweifel: Cloud-TSE-Anbindung (fiskaly, Swissbit) 4-6 Wochen einplanen
- Pilot-Vertrag: Klausel "Endkunden-Bargeld nicht Teil des Systems"

**Quelle:** Compliance 7, 00i

---

### R11 — `python-jose` CVE wird ausgenutzt vor Sprint-0-Fix

**P:** Low × **I:** High = **3**

**Beschreibung:** CVE-2024-33664 ist publiziert. Junior-Pentester findet das per `pip-audit`. JWT-Tokens können theoretisch geforged werden.

**Trigger-Event:** Sprint 0 verzögert sich &gt;2 Wochen, ein Angreifer testet gezielt

**Mitigation:**

- Sprint 0 Tag 1: G02 priorisieren (4h Aufwand, blockt nichts)
- Bis Fix: Pilot-Test-Account temporär deaktivieren bei Verdacht

**Quelle:** Security 6, 00h

---

### R12 — Onboarding-Chaos verwirrt Pilot-Azubis

**P:** High × **I:** Low = **3**

**Beschreibung:** 4 parallele Onboarding-Systeme, alle in localStorage, kein Backend-Tracking. Inkognito-Modus = Onboarding von vorne. Tooltips gebaut aber nicht aktiviert. Azubi-Perspektive 2 schreibt explizit: "ich brauche zwei Wochen Anleitung bevor ich hier was anfasse".

**Trigger-Event:** Azubi sieht zum 2. Mal Welcome-Modal, fragt "wieder?"

**Mitigation:**

- Sprint 1: Onboarding-Konsolidierung (G11) auf EIN System
- Sprint 3: Tooltip-Integration (G12) + Glossar (G13) + Sandbox (G14)

**Quelle:** Azubi 2, FE 00e, Cross-Cutting 1.10

---

### R13 — Vault-Integration verschoben → Secrets-Leck bei Server-Diebstahl

**P:** Low × **I:** Med = **2**

**Beschreibung:** 99 Variablen in `.env`-Files auf Disk. Bei Familienbetrieb (kein 24/7-Wachdienst) ist Server-Diebstahl möglich. Steuerberater-Daten würden im Klartext kopierbar sein.

**Trigger-Event:** Einbruch bei Familienbetrieb

**Mitigation:**

- Sprint 2: Vault-Integration (G25) für mind. DB-Password + JWT-Secret
- Disk-Encryption auf Server-Ebene (Bitlocker/LUKS)
- Pilot-Vertrag: Server in abschließbarem Raum (Kunden-Pflicht)

**Quelle:** DevOps 5, 00f

---

### R14 — Doku-Drift: Pilot-Kunde liest [CLAUDE.md](http://CLAUDE.md), sieht "Multi-Tenancy" — gibt es nicht

**P:** Med × **I:** Low = **2**

**Beschreibung:** Mehrere Stellen Doku/Code-Drift. [CLAUDE.md](http://CLAUDE.md) sagt WCAG 2.1 AA → 93 axe-Violations. README sagt 100% Umlaut-Accuracy → "Zuruck"-Bug. ANALYSIS sagt 70 Migrations → 227. Pilot-Kunde stellt Fragen, die Marketing-Pläne nicht beantworten können.

**Trigger-Event:** Pilot-Kunde liest Pläne im `/docs/`-Ordner

**Mitigation:**

- Monat 9: Code-Doku-Drift-Audit (G59)
- Pflege-Routine: Bei jedem Major-Feature [CLAUDE.md](http://CLAUDE.md) updaten

**Quelle:** GROUND_TRUTH §3.2, Cross-Cutting 3.2

---

### R15 — Postgres-RAM-Limit (4GB) reicht nicht bei 10+ Kunden mit pgvector

**P:** Med × **I:** Med = **4**

**Beschreibung:** RAG-Stack nutzt pgvector mit 1024-dim Embeddings. Bei 10 Kunden á 500 Docs/Monat = \~5GB Embeddings + Indexe. Plan-Cache fällt aus RAM, Queries werden 5-10x langsamer.

**Trigger-Event:** 5+ Kunden produktiv, Search-Latenz steigt von 0.5s auf 5s

**Mitigation:**

- Sofort: Postgres-RAM von 4GB auf 8GB erhöhen (G54, 1h Aufwand)
- Bei 10+ Kunden: dedizierter Postgres-Server, Read-Replicas

**Quelle:** DevOps 5, Infrastructure 00f

---

### R16 — Verfahrensdokumentation-Fehlen → GoBD-Außenprüfung-Schadenpotential

**P:** Low × **I:** High = **3**

**Beschreibung:** GoBD-BMF-Schreiben Rz. 151-155 verlangt Verfahrensdokumentation. Bei Außenprüfung des Pilot-Kunden (Familienbetrieb) ist das die erste Anforderung. Schadenpotential: Schätzungsbescheid + Verzögerungsgeld bis 250.000€.

**Trigger-Event:** Außenprüfung beim Familienbetrieb, Prüfer fragt nach Verfahrensdoku

**Mitigation:**

- Sprint 2: Verfahrensdoku als signiertes PDF (G19) — VOR Pilot-Start
- Pilot-Vertrag: Klausel "Verfahrensdokumentation wird laufend gepflegt"
- Reminder im Repo: Pro Major-Feature Verfahrensdoku updaten

**Quelle:** Compliance 7, 00i

---

### R17 — VC-Käufer-Story scheitert weil Codebase 180-250k€ wert ist, nicht 5-10M€

**P:** Med × **I:** Med = **4**

**Beschreibung:** Investor-Perspektive 11: "Bedingt investierbar, NICHT VC-Case". Wenn Ben einen 500k€-Equity-Run sucht, wird er ihn nicht bekommen. Codebase-Asset-Wert: 180-250k€ (Werkvertrag-Aufwand mit 50% Tech-Debt-Abschlag).

**Trigger-Event:** Ben pitcht VCs, bekommt Absagen, Runway läuft aus

**Mitigation:**

- Investor-Perspektive: 50k€ Brücken-Darlehen ist realistisch, nicht 500k€ Equity
- ICP-Reframe (G58) zu Family-Office-Light → Lifestyle-Business mit 30-50 Kunden Cap
- Pricing finalisieren (G57) — bei 50 Kunden á 5k€/Jahr = 250k€ ARR = lebensfähig solo

**Quelle:** Investor 11, Founder 10

---

### R18 — Pilot-Kunde weigert sich, Lexware abzuschalten

**P:** Med × **I:** Med = **4**

**Beschreibung:** Bens Pilot-Versprechen ist Migration weg von Lexware+StarMoney+DATEV+Excel. Aber Prokurist (52, 18 Jahre Lexware) will nicht. Pilot wird "parallel" zu Lexware → kein TCO-Vorteil messbar → kein Testimonial.

**Trigger-Event:** Sprint 5 Onboarding-Workshop: Prokurist zögert beim Lexware-Abschalten

**Mitigation:**

- Sprint 5.4: Pilot-Daten-Migration AKTIV vorbereiten (3 Monate Lexware-Daten in Ablage importieren)
- Pilot-Vertrag: Lexware-Abschalt-Datum verbindlich definiert
- Bei Weigerung: 2-Phase-Pilot (Phase 1 parallel, Phase 2 only-Ablage) mit explizitem Cut-over-Datum

**Quelle:** Prokurist 1, PM 9

---

### R19 — EU-AI-Act / neue Regulator-Move betrifft RAG-Stack

**P:** Low × **I:** Med = **2**

**Beschreibung:** EU-AI-Act tritt in Stufen in Kraft. Wenn lokal-LLM (Qwen3, e5-large) als "High-Risk-AI" eingestuft wird, brauchen wir Conformity-Assessment + Auditierbarkeit.

**Trigger-Event:** EU-Verordnung neue Stufe

**Mitigation:**

- DataSci 8: RAG nicht im Marketing prominent → bei Bedarf abschaltbar
- Audit-Log für RAG-Entscheidungen (existiert teilweise in `event_store.py`)
- Bei Pflicht: 2-Personen-Compliance-Team einkaufen (extern)

**Quelle:** GROUND_TRUTH §3.4, DataSci 8

---

### R20 — Solo-Founder-Burnout

**P:** Med × **I:** High = **6**

**Beschreibung:** Ben ist Solo. 60 Wochenstunden über 12 Monate ist Burnout-Garant. Bei Burnout: Pilot scheitert, Codebase verrottet, Familie leidet.

**Trigger-Event:** Ben arbeitet &gt;50h/Woche über 8+ Wochen ohne Urlaub

**Mitigation:**

- Roadmap-Disziplin: Sprint-Tasks NICHT in 4 Tagen quetschen
- Pflicht-Urlaub: 2 Wochen pro Quartal — auch wenn Pilot läuft
- Hire #2 Trigger: 3+ zahlende Kunden = Hire jetzt, nicht später
- Pilot-Phase: Daily-Check-in zwingend, NICHT 24/7-Notdienst

**Quelle:** Investor 11, Founder 10, persönliche Beobachtung

---

## Tier 3: Mittlere Risiken (Score 1-3)

R#RisikoP×IMitigation-KurzR21Lexware verklagt wegen "Lexware-Verdrängung"-MarketingL×L=1Marketing-Sprache neutralisierenR22Ben wechselt Wohnort, Server-Standort brichtL×M=2Server-Standort vertraglich pinnenR23Frontend-Build-Pipeline zeigt Source-Maps in ProductionL×M=2Source-Map-Upload nur an SentryR24Open-Source-LLM (Qwen3) wird kommerziell beschränktL×L=1Plan-B: Open-Hermes/Llama als FallbackR25Customer-Sue wegen Datenverlust durch Silent-CatchesL×H=3G15 Sprint 1 — Silent-Catches sweepenR26Pilot-Vertrag-Klauseln (DSGVO-DPA) fehlenM×L=2G50 Monat 5 — DSGVO-DPA-Templates

---

## Risiko-Heatmap

```
              Impact:
               L   M   H
Wahrsch:  H  R12 R04 R01,R02
          M  R14 R07,R08,R09,R15,R17,R18 R03,R20,R05
          L  R21,R23,R24 R13,R19,R22 R06,R10,R11,R16
```

**Hot-Zone (P=High, I=High):** R01, R02 → Sprint 0 absolute Priorität **Hot-Zone (P=Med, I=High):** R03, R20, R05 → strategisch + persönlich beachten

---

## Trigger-Watch-Liste (Was Ben wöchentlich prüfen sollte)

1. **Slack-Notification-Test:** Funktioniert noch? (R01)
2. **CVE-Status:** `pip-audit` neue Findings? (R02, R11)
3. **Eigene Arbeitsstunden:** &gt;50h/Woche über 4 Wochen? (R20)
4. **Pilot-Kunden-Zufriedenheit:** Daily-Check-in Punktzahl &lt;7? (R07, R18)
5. **Code-File-Größe:** Neue Files &gt;30KB? (R08)
6. **Backup-Restore-Test:** Letzter erfolgreicher Test &lt;30 Tage? (R06)
