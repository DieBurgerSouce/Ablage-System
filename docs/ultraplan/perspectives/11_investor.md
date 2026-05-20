# 11 - Investor / CFO Perspektive

Datum: 2026-05-03. Lens: Cashflow, nicht Code. Hartmodus.

---

## 1-Sentence-Verdict

**Bedingt investierbar — als Lifestyle-Business mit 30-50 Kunden Cap fuer Ben, NICHT als VC-Case; ein 500k-EUR-Equity-Investment macht keinen Sinn, ein 50k-EUR-Bruecken-Darlehen gegen die ersten 10 Pilotvertraege schon.**

---

## 2. Unit-Economics (pro Kunde, On-Premises-Modell)

| Position | EUR/Jahr | Anmerkung |
|---|---:|---|
| Hardware (RTX 4080 Box, 36 Mon AfA) | 500 | 1.500 EUR / 3 Jahre |
| Lizenz / Subscription (zu kalkulieren) | **3.600** | Annahme: 300 EUR/Mon = 25-30 % der versprochenen 7k Ersparnis |
| Onboarding (einmalig, auf 3 Jahre verteilt) | 800 | 2-3 Tage Solingen-Vor-Ort + Setup + DATEV-Mapping |
| Support (Ben-Stunden, 4h/Mon a 80 EUR) | 3.840 | konservativ; KMU rufen viel an |
| Hosting / GPU-Strom (beim Kunden) | 0 | on-prem, Kunde zahlt |
| Software-Updates / Migrationen | 600 | Patches, GoBD-Updates, DATEV-Schluesselrahmen |
| **Gesamt-Cost-to-Serve** | **5.740** | |
| **Versprochene Ersparnis (Pilot-Promise)** | 7.000 | Bens Pilot-Versprechen |
| **Theoretischer ARR-Headroom** | 1.260 | Differenz Versprechen <-> Cost-to-Serve |

**Befund**: Bei 7k EUR Promised-Saving ist die **Zahlungsbereitschaft des Kunden gedeckelt bei ~3.500-4.500 EUR/Jahr** — sonst lohnt es fuer ihn nicht. Die Cost-to-Serve **5.740 EUR ueberschreitet die zahlbare ARR**. Die Rechnung trägt nur, wenn:
1. Support-Stunden auf <2h/Mon gedrueckt werden (Self-Service-UI muss funktionieren — siehe Frontend-Audit)
2. ODER ARR auf 4.800-6.000 EUR steigt (Wert ueber GoBD-Compliance + DATEV-Export, nicht nur Zeitersparnis)

| Metric | Wert | Begruendung |
|---|---:|---|
| **ARR-Min (Break-Even pro Kunde)** | **4.800 EUR** | Cost-to-Serve + 20 % Marge |
| **CAC-Plausibel (KMU DE)** | **3.500-6.000 EUR** | Steuerberater-Empfehlung + 1-2 Termine + Pilot-Phase + Aufsetzen |
| **LTV-Plausibel (5 Jahre, ARR 4.800)** | **18.000 EUR** | Discount 5 % p.a., 25 % Churn ueber 5 Jahre |
| **LTV/CAC-Ratio** | 3.0-5.1x | Akzeptabel fuer KMU-Software, aber NICHT fuer VC (Ziel 5-10x) |
| **Break-Even-Kunde Nr.** | **#22-28** | siehe Burn-Rate unten |
| **Payback-Period CAC** | 9-15 Monate | tolerabel fuer Bootstrap, zu lang fuer VC |

**Brutaler Reality-Check**: Wenn der Kunde nur 3.600 EUR/Jahr zahlt UND Ben 4 Stunden/Monat Support leistet, **verliert Ben Geld pro Kunde** — er subventioniert mit eigener Zeit. Das ist OK fuer die ersten 5 Pilotkunden (Lernkurve), aber nicht skalierbar.

---

## 3. Bus-Faktor-1-Mitigations-Plan

Bus-Faktor heute: **1 (Ben).** 797 Services, 227 Migrationen, 299 Routes, 95 Model-Files. Komplette Domain-Knowledge konzentriert.

| Mitigation | Aufwand | Wirkung | Empfehlung |
|---|---|---|---|
| **Code-Escrow** bei Notar (jaehrliche Abgabe Quelltext + Build-Anleitung) | 1 Tag + 800 EUR/Jahr | Kunde kann bei Bens-Ausfall System weiterbetreiben -> verkaufsfoerdernd | **JA, sofort** |
| **DR_RUNBOOK + Operations-Doku** (existiert teilweise, aber Solo-Wissen) | 5 Tage | Vertretung kann System fuer 2-4 Wochen am Leben halten | **JA, Phase Pilot-Start** |
| **Externer Vertretung** (Freelance-Backend-Engineer auf Retainer 500 EUR/Mon) | 6.000 EUR/Jahr | Krankheit/Urlaub abgedeckt | **NACH Kunde Nr. 5** |
| **Buehne-Frei-Klausel** (Vertraege: Kunde kann mit 30 Tagen Anschlussservice wechseln) | 0,5 Tage | Vertrauen, kein Lock-in-Risiko fuer Kunden | **JA, sofort** |
| **Berufsunfaehigkeitsversicherung** fuer Ben | 80-150 EUR/Mon | persoenliche Absicherung | **JA, sofort** |
| **Co-Founder / Junior-Hire** | 60-90k EUR/Jahr | strukturelle Loesung | **NACH Kunde Nr. 15-20** |
| **Verkaufsfaehigkeit dokumentieren** (Architecture Decision Records, Migrations-Index) | 3 Tage | erhoeht Asset-Wert um 30-50 % | **JA, Q3 2026** |

Bus-Faktor 1 ist heute der groesste **finanzielle** Risikofaktor — wichtiger als die God-Objects, wichtiger als Multi-Tenancy. Ein einziger Krankenhaus-Aufenthalt von Ben killt alle Kundenvertraege binnen 60 Tagen.

---

## 4. Time-to-Profitability / Burn-Rate

**Bens persoenliche Burn-Rate (Solingen, Solo, ohne Familie zahlbar)**:

| Position | EUR/Mon | Anmerkung |
|---|---:|---|
| Lebenshaltung Solingen (1-Person, mittel) | 1.800 | Miete 700, Lebensmittel 400, Versicherungen 250, Mobilitaet 200, Sonstiges 250 |
| Krankenversicherung (PKV/GKV freiwillig) | 450 | KSK / freiwillig gesetzlich |
| Renten- + BU-Vorsorge (Mindest) | 250 | sonst Altersarmut |
| Steuerberater | 150 | unverzichtbar |
| Hosting / Tools / Subscriptions (Claude, GitHub, etc.) | 350 | aktuell sichtbar |
| Office / Buero zu Hause | 0 | |
| Puffer / Unvorhergesehenes | 200 | |
| **Gesamt-Burn (Privat + Business)** | **3.200** | |
| **Jahres-Burn** | **38.400** | |

**Runway-Szenarien**:

- **Mit 0 EUR Reserven**: 0 Monate. Pilotkunde #1 muss <60 Tage zahlen.
- **Mit 30k EUR Reserven (typisch fuer Solo-Founder mit Vorgeschichte)**: 9 Monate.
- **Mit 50k EUR Reserven**: 16 Monate.

**Break-Even-Kunde** (bei Marge 1.260 EUR/Kunde/Jahr, siehe oben):
- Burn 38.400 EUR / 1.260 EUR pro Kunde = **31 Kunden** noetig nur fuer Bens Burn-Rate
- Bei optimistischer Marge 2.500 EUR/Kunde (ARR 5.500, Cost 3.000): **16 Kunden**

**Brutaler Reality-Check**: 31 Kunden bei einem Solo-Operator mit On-Premises-Hardware-Termin pro Kunde = **mindestens 24 Monate Akquise**. Ohne Reserven oder Vorfinanzierung: nicht machbar. Mit 50k Bruecke und 1 Pilotkunde alle 5-8 Wochen: knapp.

---

## 5. Scale-Constraints (was bricht zuerst bei #N Kunden?)

| Kunden-N | Erstes Bottleneck | Code-Beleg | Fix-Aufwand |
|---|---|---|---|
| **5** | Bens Aufmerksamkeit (Onboarding 2-3 Tage/Kunde + 4h/Mon Support) | menschlich | nicht skalierbar |
| **10** | Out-of-Hours-Notification (Alertmanager-Slack auskommentiert, Mail an `ops-team@internal.local` ohne Auth) | Audit 00f §11 | 30 Min |
| **15** | Solo-Wissens-Bottleneck — niemand kann Ben vertreten | Audit 00b: 797 Services | 6-12 Mon Co-Hire |
| **20** | Codebase-Wartbarkeit: God-Objects (118 KB `structured_extraction_service.py`, 99 KB `tax_optimization_service.py`, 88 KB Logik in `streckengeschaeft/__init__.py`) | Audit 00b §2 | 4-8 Wochen Refactoring |
| **30** | Multi-Tenancy: keine echte Mandanten-Trennung (1 DB-Spalte `tenant_id` referenziert Mieter, NICHT Mandanten) | Audit 00b §10 | 3-4 Monate Re-Architektur ODER on-prem-pro-Kunde-Modell beibehalten |
| **50** | Postgres-Tuning (4 GB RAM-Limit), GPU/VRAM-Konkurrenz (kein Compose-Limit), 56x `except: pass` schlucken Fehler | Audit 00f §1, 00b §6 | 2-3 Wochen |
| **100** | Hardware-Logistik: 100 RTX-4080-Boxen verteilen, warten, ersetzen — Solo-Operator-Ende | physisch | Strukturwandel |

**Was bricht ZUERST**: Bens Zeit. Ab Kunde #10 wird er 50% seiner Woche mit Support verbringen, statt zu entwickeln. Die Codebase haelt mehr aus als der Mensch.

---

## 6. IP-Wert (was ist heute monetarisierbar?)

Verkaufsfaehigkeit der einzelnen Komponenten (heute, nicht in 12 Monaten):

| Komponente | Wert standalone | Begruendung |
|---|---|---|
| **Streckengeschaeft-Detection** (4-Stage-Cascade, separate Migrations 001-004) | **30-60k EUR** als Lizenz an Spezial-Software-Hersteller (DATEV-Partner-Ecosystem); im Markt rar | spezifisch DE-KMU-Use-Case, hoher Erkenntniswert fuer Steuerberater |
| **EventStore Hash-Chain** (`event_sourcing/event_store.py`, kanonisches JSON + SHA-256, Verify-Pfad) | **50-120k EUR** als GoBD-Audit-Service-Modul fuer DATEV/Lexware | echter Audit-Anker, kein Theater (Audit 00b §9) |
| **Multi-Backend OCR-Pipeline** (DeepSeek + GOT + Surya, Self-Learning) | 20-40k EUR Lizenz | aber Commodity wird, Open-Source-Alternativen werden besser |
| **DATEV-Connect-Integration** (vollstaendige SKR03/04, Vendor-Mapping, 30 KB Code) | 40-80k EUR fuer DATEV-Marketplace-Listing | hoeher monetarisierbar als Komplettpaket |
| **Mahnwesen B2B/B2C BGB §286/288 Logic** | 10-20k EUR | gibt's anderswo, aber gut gemacht |
| **Kassenbuch APPEND-ONLY mit Hash-Chain** | enthalten in EventStore-Wert | |
| **Codebase als Ganzes** (797 Services, 227 Migrationen) | siehe Asset-Wert §10 unten | "Sammlung von Implementierungen", nicht Produkt |

**Was ist heute SOFORT verkaufbar?** Der **Streckengeschaeft-Detector** und die **Hash-Chain-EventStore-Implementierung** sind beide IP-Inseln, die ein Spezialist-Kaeufer (DATEV-Partner, Audit-Software-Hersteller) als Komponente lizenzieren wuerde. Der Rest ist "kompetent gebauter aber nicht patentfaehiger Standard".

---

## 7. Compliance-Liability (wer haftet bei GoBD-Verstoss?)

**Brutal**: Bei Software-Bug, der zu GoBD-Verstoss beim Kunden fuehrt, haftet der **Kunde** gegenueber Finanzamt — nicht Ben. ABER Kunde regressiert gegen Ben. Maximaler Schadensersatz im Software-Lizenzvertrag laut UN-Kaufrecht / BGB ist meist auf "Lizenzgebuehren der letzten 12 Monate" begrenzt — ABER diese Klausel haelt vor Gericht NICHT bei grober Fahrlaessigkeit.

**Konkrete Risiken aus Audit**:
- 56x `except Exception: pass` an Compliance-Stellen (Audit 00b §6: `access_analytics_service.py:840`, `imports/*` mehrfach) — das ist **grobe Fahrlaessigkeit-Indikator**, weil Audit-Events stumm verloren gehen
- `predict_payment_probability` Stub (`return 0.7`) — wenn Mahnverfahren auf falscher Wahrscheinlichkeit basiert: Vorsatz-Verdacht
- Multi-Tenant-Backfill in Migration 257-261 noch nicht abgeschlossen

**Versicherungs-Loesung**: Berufshaftpflicht IT-Solo-Selbststaendige ca. 1.200-2.400 EUR/Jahr, deckt 1-3 Mio EUR. **Pflicht ab Kunde #1.** Ohne diese Versicherung ist Ben persoenlich mit Haus + Konto haftbar.

**Vertragliches Mitigation**:
- Haftungsausschluss "ausser bei Vorsatz/grober Fahrlaessigkeit" 
- Mitwirkungspflicht des Kunden (Backups pruefen, Plausibilisieren)
- Auftragsverarbeitungs-Vertrag (AVV) DSGVO-konform
- Schiedsgerichtsklausel statt Amtsgericht (verhindert oeffentliche Praezedenzfaelle)

---

## 8. Cloud-Pivot-Faehigkeit

Falls On-Premises scheitert (Hardware-Logistik, RTX-Lieferprobleme, Kunden wollen Cloud) — wie schwer ist Cloud-Pivot?

**Hard**:
- Multi-Tenancy fehlt komplett (Audit 00b §10): `tenant_id` ist Mieter-ID. Ohne Row-Level-Security oder Schema-per-Tenant ist Cloud-Multi-Tenant unmoeglich. Aufwand: **3-4 Monate** Re-Architektur.
- GPU-Cost: RTX-4080-On-Prem (1.500 EUR einmalig) wird Cloud zu A100/H100 (~3-8 EUR/Stunde) — bei 24/7-Betrieb 22-58k EUR/Jahr pro Kunde. Wirtschaftlichkeit kaputt fuer KMU-ARR von 4.800 EUR.
- DSGVO: deutsche KMU verlangen on-prem oder zumindest deutsche Cloud (OVH, IONOS, T-Systems) — kein AWS/GCP/Azure ohne Reibung.

**Halb-Pivot (DE-Cloud, Single-Tenant pro Kunde)**: Machbar in 4-6 Wochen, aber Wirtschaftlichkeit suboptimal. ARR muesste auf 8-12k EUR/Jahr steigen.

**Realistische Cloud-Variante**: Hybrid — Daten + DB on-prem beim Kunden, Compute (OCR/RAG) in deutscher Cloud. Aufwand: **6-10 Wochen**. Sinnvoll wenn 3+ Kunden GPU-Hardware ablehnen.

---

## 9. Exit-Optionen (real, mit Wahrscheinlichkeit)

Ben ist heute Solo, 1 Codebase, 0-1 Kunden. Realistische Exit-Szenarien:

| Szenario | Kaeufer | Wahrscheinlichkeit | Bewertung |
|---|---|---:|---|
| **Asset-Sale** (Codebase-Lizenz an einen DATEV-Partner / mittelgrossen Software-Haus) | DATEV-Marketplace-Anbieter, mid-market ERP-Hersteller (e.g. Sage Partner) | **35 %** | 80-200k EUR |
| **Acqui-Hire** durch lexoffice / sevDesk / BillBee (Talent + IP) | Haufe-Lexware Group, sevDesk (Sage-eigen), BuchhaltungsButler | **15 %** | 150-350k EUR + Anstellung Ben 2-3 Jahre |
| **Strategischer Kauf durch DATEV** als reine IP-Akquisition (Streckengeschaeft + Hash-Chain) | DATEV eG | **5 %** | 200-500k EUR; DATEV kauft selten extern, baut intern |
| **Strategischer Kauf durch d.velop** (DMS-Markt, Synergie mit dem Document-Layer) | d.velop AG | **8 %** | 300-700k EUR; d.velop ist akquise-aktiv im DMS-Mittelstand |
| **Lifestyle-Verkauf** (kleiner Kaeufer, 30-50 Kunden Buch, ueber MicroAcquire/Indiehackers-Markt) | individueller Microacquirer, regionaler IT-Dienstleister NRW | **30 %** | 2-3x ARR (also 250-500k EUR bei 30 Kunden a 5k ARR) |
| **Kein Verkauf, Run-the-Business** (Lifestyle, 30-50 Kunden, 100-150k Gewinn/Jahr) | — | **40 %** (Default-Pfad fuer Solo-Founder) | 0 EUR Exit, aber 7-10 Jahre Cashflow |

**Wahrscheinlichkeitsuumme >100 % weil Szenarien sich teilweise ueberlappen** (z.B. Lifestyle-Run dann Asset-Sale Jahre spaeter).

**Realistische Exit-Erwartung in 3-5 Jahren**: 200-400k EUR, mit ~50 % Konfidenz. **Kein Unicorn-Pfad sichtbar.** Das ist ein **Mittelstand-Software-Asset**, kein VC-Fall.

**DATEV / Lexware Wahrscheinlichkeits-Realismus**: DATEV ist eine Genossenschaft und kauft fast nichts extern. Lexware (Haufe-Lexware) hat einen eigenen DMS-Stack (lexoffice). d.velop ist der realistischste Strategic — sie suchen Mittelstand-DMS-Komponenten. **Kein Pitch heute** — erst bei 20+ Kunden + bewiesener Retention.

---

## 10. Asset-Wert heute (in EUR)

Wenn Ben **heute** verkaufen wollte (0 Kunden, kein ARR, nur Codebase + Domain-Knowledge):

| Komponente | Wert |
|---|---:|
| Codebase (797 Services, 227 Migrationen, 678 Tests) — Bewertung als Werkvertrag-Aufwand | 180-250k EUR (geschaetzt 2.000-2.500 Personen-Stunden a 80 EUR Senior-Rate, abgezinst 50 % wegen Tech-Debt + God-Objects) |
| Domain-Knowledge (DATEV-Connect, Streckengeschaeft, GoBD-Hash-Chain) — als IP-Kompetenz | 50-100k EUR (verkaufsfaehig nur mit Ben als Embedded Consultant fuer 6-12 Monate) |
| Brand / Pilot-Versprechen / Marketing | 0-5k EUR (es existiert noch keine Marke, kein Inbound, kein Case Study) |
| Kundenbasis | 0 EUR (noch keine zahlenden Kunden) |
| **Asset-Wert heute, ohne Kunden** | **180-300k EUR** |
| **Asset-Wert mit 5 Pilotkunden (12 Mon Retention bewiesen)** | **300-450k EUR** (2-3x ARR + Codebase-Discount) |
| **Asset-Wert mit 20 Kunden** | **500-800k EUR** |

**Brutaler Vergleich**: Ein deutscher Senior-Backend-Engineer kostet bei 80 EUR Stunde + Festanstellung ~120-140k EUR/Jahr. Bens 2 Jahre Solo-Build entsprechen 240-280k EUR Personal-Aequivalent — der **untere Asset-Wert heute deckt sich erstaunlich genau mit der "alternativen Vergleichsrechnung"**. Es gibt keine Premium-Bewertung ohne Kundenstamm.

---

## 11. Top-3 finanzielle Staerken

1. **Hardware-Cost-Pass-Through**: 1.500 EUR RTX-4080 zahlt der Kunde — keine GPU-Cost auf Bens Bilanz. Strukturell deflationaerer Margenanker als Cloud-Konkurrenz. Bei 100 Kunden hat Ben 0 EUR GPU-Investment.
2. **Mehrere monetarisierbare IP-Inseln**: Streckengeschaeft-Detector und GoBD-Hash-Chain sind verkaufsfaehig auch ohne SaaS-Geschaeft. Doppelter Exit-Pfad (Produkt vs. Lizenz).
3. **Bootstrap-Pfad ist schmal aber existent**: Mit 50k EUR Bruecke + 5 Pilotkunden in 9 Monaten ist Break-Even erreichbar. Kein Equity-Verwaesserungs-Zwang.

---

## 12. Top-5 finanzielle Risiken

1. **Bus-Faktor 1** (groesstes finanzielles Risiko, schwerer als jeder Code-Bug): Bens Krankheit/Burnout = 100 % Asset-Wert-Verlust binnen 60 Tagen. Kein Versicherungsprodukt deckt das fuer Software-Solo-Founder.
2. **Cost-to-Serve uebersteigt zahlbare ARR**: 5.740 EUR Cost-to-Serve vs. ~3.600-4.500 EUR realistische Kunden-Zahlungsbereitschaft. Marge negativ pro Kunde, wenn Support-Stunden nicht radikal reduziert werden.
3. **Compliance-Haftung ohne Berufshaftpflicht**: 56x `except: pass` an Compliance-Stellen + Mahnwesen-Stub kombiniert mit GoBD-Promise = Schadensersatzrisiko 6-stellig pro Kunde bei Vorsatz-Vorwurf. Pflichtversicherung kostet 1.200-2.400 EUR/Jahr und **wurde noch nicht abgeschlossen** (Annahme).
4. **Wettbewerbs-Druck Cloud-Anbieter**: lexoffice (10 EUR/Mon, 5min Setup), sevDesk, BuchhaltungsButler etablieren Self-Service-Bedienbarkeit, die Bens On-Premises mit 2-3 Tagen Onboarding nicht bieten kann. KMU-Markt waehlt zunehmend Cloud trotz DSGVO-Bedenken.
5. **Liquiditaets-Gap zwischen Pilot #1 und Break-Even (Kunde #22-31)**: 24+ Monate ohne strukturelle Externfinanzierung. Wenn Ben keine 50k Reserven hat: **finanziell unmoeglich** ohne Nebenjob/Freelance, der Build-Time wegnimmt.

---

## 13. Note: Investment-Tauglichkeit

**4 / 10**

Begruendung:
- Plus: monetisierbare IP-Inseln, Bootstrap-Pfad existiert, Hardware-Pass-Through, kompetente Codebase
- Minus: Bus-Faktor 1 strukturell, Cost-to-Serve > zahlbare ARR (Kern-Modell wackelt), kein Multi-Tenant-Cloud-Pivot ohne 3-4 Monate Re-Arch, Liquiditaets-Gap 24 Monate, Markt frisst KMU-On-Prem zugunsten Cloud-Self-Service

Eine 4 heisst: **kein klassisches VC- oder Angel-Investment-Case**. Geld investiert sich gegen Cashflow, hier wird Cashflow erst in 24+ Monaten erwartet, mit hohem Personenrisiko.

**Investierbar JA, wenn**: 50k EUR Bruecke, an die ersten 5 Pilotkunden gekoppelt, Konvertierung in 5-15 % Equity bei Erreichen 10 Kunden — das ist Bridge-Finanzierung, keine Venture-Wette.

**Investierbar NEIN, wenn**: 250k+ Equity-Investment fuer 20 % Anteil mit Wachstumserwartung. Das passt zu einer Codebase, die einen 100k-EUR-Asset-Wert hat — nicht zu einer 1,25-Mio-EUR-Bewertung.

---

## 14. 3 finanzielle Empfehlungen fuer Ben

1. **Sofort: Berufshaftpflicht IT (1.200-2.400 EUR/Jahr) + Code-Escrow + AVV-Vertraege.** Bevor Pilotkunde #1 zahlt. Ohne diese drei Bausteine ist jeder Kundenvertrag ein persoenliches Insolvenz-Risiko bei einem GoBD-Bug.

2. **Preis-Test in der Pilotphase**: Statt 300 EUR/Mon zu setzen, einen Pilot-Vertrag mit Multi-Tier-Pricing testen — 4.800 / 7.200 / 12.000 EUR ARR-Stufen, je nach Modulen (Banking + Mahnwesen + Streckengeschaeft als Premium). Beobachten, was Kunden tatsaechlich zahlen — die "7k Ersparnis"-Promise rechtfertigt mindestens 40 % Wertabschoepfung (~2.800 EUR/Jahr); pruefen, ob Kunden bereit sind, 4.800-6.000 EUR zu zahlen, weil der wahre Wert in **GoBD-Compliance** und **DATEV-Vermeidung von Steuerberater-Stunden** liegt — nicht in Zeitersparnis.

3. **Asset-Verkaufs-Plan parallel zum Produkt**: Streckengeschaeft-Detector und Hash-Chain als Lizenz-Modul DATEV-Partnern oder d.velop anbieten — auch wenn das Produkt-Geschaeft erfolgreich laeuft. Diese parallele Monetarisierung (50-120k EUR Einmal-Lizenz) macht Bens Unternehmen unabhaengig von Pilot-Geschwindigkeit und schafft sofortigen Cashflow zur Finanzierung der KMU-Akquise. Wenn Pilot-Geschwindigkeit nicht reicht (Kunde #5 nicht in 6 Monaten erreicht), ist die IP-Lizenzierung der schnellere Cashflow-Pfad als das SaaS-Produkt.

---

**Bottom-Line des Investors**: Das ist ein gut gebautes Lifestyle-Asset mit 30-50-Kunden-Cap und einem realistischen 2-3-Jahres-Exit zwischen 200-400k EUR. Es ist **kein Investment-Vehikel im klassischen Venture-Sinn**, aber es ist auch **keine wertlose Hobby-Codebase**. Die richtige Finanzierungsform ist eine 50k-Bruecke + Convertible Note, **nicht** eine Equity-Runde — Ben sollte die Kontrolle behalten, weil ohne ihn das Asset 80 % seines Werts verliert.

(Wortzahl: ~1750)
