# 10 — Founder/CEO Perspective: Build, Pivot oder Bury?

**Datum:** 2026-05-03
**Rolle:** Founder/CEO. 12 Monate Runway. Solingen. Solo.
**Modus:** Brutal. Keine Höflichkeit.

---

## 1-Satz-Verdict

**Pilot beim Familienbetrieb JA — aber das Produkt darf NICHT als "Cloud-Alternative für deutsche KMU" auf den Markt; das ist ein Kindheits-ICP. Reframe oder pivotiere innerhalb 90 Tagen, sonst bury.**

---

## Wettbewerbs-Tabelle (KMU 5–200 MA, DE, Eingangsrechnung-Workflow)

| Kriterium | lexoffice | sevDesk | DATEV Online | d.velop docs | Windows-Ordner | Ablage-System |
|-----------|-----------|---------|--------------|--------------|----------------|---------------|
| Setup-Zeit (Erstkunde) | 5 Min | 5–10 Min | 1–3 Tage (StB) | 4–12 Wochen | 0 Min | **2–5 Tage** (Solo-Founder Onboarding, 32 Container, GPU-Box) |
| Preis (KMU 10 MA, Jahr) | ~120–600 € | ~250–700 € | ~600–1.800 € (StB) | ~5.000–25.000 € + Lizenz | 0 € | Perpetual ~5.000–15.000 € + ~1.500 €/Jahr Maintenance (geschätzt) |
| Hardware-Aufwand Kunde | 0 (SaaS) | 0 | 0 | Server + IT | vorhanden | **RTX-4080-Workstation Pflicht (~2.500 €)** |
| OCR-Qualität DE | mittel (Cloud) | mittel | StB-handisch | gut (DocuWare-Niveau) | 0 | **sehr gut** (Multi-Backend, DeepSeek/GOT, Umlaut-Loss) |
| GoBD-Konformität | ja, zertifiziert | ja, zertifiziert | ja, der Standard | ja | nein | DB-Trigger, Hash-Chain, **keine Zertifizierung** |
| DATEV-Schnittstelle | ja, zertifiziert | ja | nativ | ja | nein | Buchungsstapel + OAuth, **nicht zertifiziert** |
| Mahnwesen BGB §286/288 | ja (basic) | ja (basic) | ja | über Plugin | nein | ja, B2B/B2C-differenziert (4/5) |
| Streckengeschäft | nein | nein | manuell | nein | nein | **5/5, 4-Stage-Detection** |
| Privatvermögen-Modul | nein | nein | nein | nein | nein | **38 Services** (separater Bounded Context) |
| RAG/AI-Chat über eigene Akten | nein | nein | nein | teilweise | nein | geplant (Status: real teils, teils Plan) |
| On-Prem / keine Cloud | nein | nein | nein | ja | ja | **ja** |
| Steuerberater-Akzeptanz | ~80% (DATEV) | ~30% | ~80% | ~10% | 100% (Fluch) | **0% Marktbekannt** |
| Sales-Cycle | Self-Service | Self-Service | StB sagt's | 6–12 Monate | – | unbekannt, vermutlich 3–9 Monate |
| Support bei Crash | 24/7 Hotline + Status-Page | 24/7 | StB | dediziertes Sales/Support-Team | Karl-Heinz aus IT | **Ben. Allein.** |

**Quellen:** lexoffice/sevDesk/DATEV Marketing-Pages (öffentlich); d.velop-Implementierungszeit aus Branchen-Benchmarks; Ablage-Werte aus Audits 00b, 00f, 00i, 00j.

---

## Killer-Frage: Wer kauft Ablage-System statt lexoffice?

**Nicht der typische 10-MA-Handwerksbetrieb.** Der nimmt lexoffice in 5 Minuten und ist fertig.

Realistischer ICP-Schnitt — Kunden, für die Ablage-System tatsächlich besser ist:

1. **Datenschutz-Paranoide / On-Prem-Pflicht-Branchen** — Anwaltskanzleien, Arztpraxen, Steuerberater selbst, sicherheitskritische Zulieferer (Rüstung/Medizintechnik), öffentliche Träger. Cloud ist No-Go aus rechtlichen oder Berufsordnungs-Gründen. Markt: enger, aber zahlungskräftig.
2. **Familienbetriebe mit komplexen Sondergeschäften** — Streckengeschäft, Drop-Shipment, internationale Lieferketten mit OCR über Russisch/Polnisch (Translation-Pipeline-Plan). lexoffice/sevDesk decken das nicht ab. DocuWare wäre teurer.
3. **Privatvermögen + Geschäft als integrierte Akte** — der „Ben-Use-Case". Unternehmer mit Immobilien, Beteiligungen, Familienvermögen. Niemand sonst kombiniert das. **Aber: Markt ist klein** (~10–50k Adressen DE).
4. **Daten-Souveränitäts-Käufer mit RAG-Bedarf** — wollen mit eigenen Akten chatten, ohne dass das in OpenAI/Microsoft fließt. Markt wächst, aber Konkurrenz formiert sich gerade (private LLM-Stacks).

**Brutaler Kern:** Der Markt für „on-prem Eingangsrechnungen für KMU 5–200 MA" ist faktisch von DATEV besetzt (über die Steuerberater) und von lexoffice/sevDesk (über Self-Service). Ablage-System landet in einer Nische **Unter-50-MA-Premium-on-prem-mit-Sondergeschäft**. Das ist kein Massen-Markt. Das ist ein Boutique-Markt.

---

## Top-3 Stärken (aus Founder-Sicht)

1. **Backend-Tiefe ist real und ohne Konkurrenz im KMU-Segment.** GoBD mit DB-Triggern, Hash-Chain, Streckengeschäft 5/5, 14 OCR-Backends mit Umlaut-Loss-Function, Multi-Tenancy-Backfill in Arbeit (Audit 00b/00i/00k). Das baut keiner in 12 Monaten nach. Selbst wenn DocuWare oder ELO sich einen kompetenten Berater holen, sind sie 18 Monate hinten.
2. **Privatvermögen als integrierter Bounded Context (38 Services).** Niemand sonst macht das. Wenn der ICP zu „Family Office Light für Mittelstand-Patriarchen" verschoben wird, wird das ein sticky Differentiator. Hier liegt vermutlich das echte Geschäftsmodell.
3. **Du hast einen Pilot-Kunden mit Existenz-Recht (Familienbetrieb).** Kein Pitch-Deck-Theater. Echte Daten, echte Workflows, echtes Feedback. 7.000 €/Jahr-Einsparung pro Kunde ist ein realer Wert. Das ist ein 6–8-Kunden-Track-Record innerhalb 12 Monaten erreichbar — bei richtigem ICP.

---

## Top-5 Strategische Risiken

1. **Scope-Bloat ist tödlich.** 797 Services, 257 API-Files, 95 Model-Files, 4-fache Codebase-Größe in 5 Monaten (Ground-Truth §1.1). `ai/` als Top-Bucket mit 52 Files ist ein Smell (Audit 00b). 10 leere `__init__.py` (`ai_ethics/`, `ceo_dashboard/`, `knowledge_graph/`, `scanner/`...) sind Roadmap-Theater. **Das ist keine Stärke, das ist ein Anker.** Du baust schneller als du fokussierst. In 12 Monaten Solo-Founder schaffst du keine zweite Verdopplung — du musst entkernen.
2. **Solo-Founder + Enterprise-Software auf Kunden-Hardware skaliert mathematisch nicht.** 32-Service-Compose-Stack (Audit 00f) auf Kunden-RTX-4080. Kein GPU-VRAM-Limit. Wenn bei Kunde #3 nachts der Backend-Container crasht (Audit 00j: bei Walk war Backend offline → Pilot-Risiko verifiziert), bist DU der Pager. Bei 10 Kunden bist du 24/7 im Eskalations-Modus. Bei 20 Kunden bist du tot.
3. **Steuerberater-Marktanteil = 80% bei DATEV. Du gehst nicht am StB vorbei.** Wenn der StB des Pilotkunden sagt „nimm DATEV Online, das exportiere ich blind", ist das Spiel vorbei — egal wie gut deine GoBD-Trigger sind. Du brauchst eine Steuerberater-Akquise-Strategie. Aktuell hast du keine.
4. **Compliance-Beweisbarkeit fehlt für Pilot-Verkauf.** Verfahrensdokumentation existiert nicht persistiert (Audit 00i §2.1), KOSIT-Validator fehlt für E-Rechnung (§6.3), DATEV-Zertifizierung fehlt (§5.8), TSE-Anbindung unklar. Im Verkaufsgespräch fragt jeder StB: „Sind Sie GoBD-zertifiziert?" — Antwort heute: „Nein, aber wir haben DB-Trigger." Der StB winkt ab.
5. **Live-System-Zustand am Audit-Tag: Backend offline (Audit 00j).** Das ist mehr als ein technisches Problem. Es zeigt: niemand fährt das System regelmäßig live als End-User. Du arbeitest am Code, nicht am Produkt. Wenn am Pilot-Tag dasselbe passiert, ist der Pilot-Kunde verloren. JWT in Response-Body statt httpOnly-Cookie (Audit 00h Top-Lücke 1) ist ein Pilot-Blocker, der seit Dezember in der Doku als „behoben" markiert wurde — aber Code widerspricht. Das ist ein strukturelles Vertrauens-Problem.

---

## Pflichtfragen-Antworten

### 1. ICP-Klarheit
**„Deutsche KMU 5–200 MA" ist Wunschdenken.** Real-ICP nach Audit-Lage:
- **Land:** DE (Solingen-Hub, Sprache, Compliance)
- **Branche:** datenschutzkritisch (Recht, Medizin, Öffentlich) ODER Familienbetrieb mit Sondergeschäft (Handel/Streckengeschäft) ODER UHNW-Familie mit integriertem Privatvermögen
- **Größe:** 5–30 MA, nicht 200 (Support-Skalierung)
- **Budget:** 5–20 k€ Initial + 1–3 k€/Jahr (Boutique-Segment)
- **Pain:** Cloud-No-Go, komplexe Workflows, oder integrierter Privat+Geschäft-Bedarf

**Evidenz für 5–200 MA-Pitch:** Keine. Nur Wunsch.

### 2. Wettbewerb-Reality-Check
Siehe Tabelle oben. Ablage-System gewinnt **nur** bei On-Prem-Pflicht + Sondergeschäft + integriertem Privatvermögen. Verliert bei Setup-Zeit, Preis, Steuerberater-Akzeptanz, Support-Skalierung, Marktbekanntheit.

### 3. Moat
- **Backend-Tiefe in Spezialfeatures (Streckengeschäft, Privatvermögen, Multi-OCR mit Umlaut-Loss):** ja, schwer kopierbar, 12+ Monate Aufholzeit für Wettbewerber.
- **GoBD-Trigger + Hash-Chain auf DB-Ebene:** nice-to-have, aber jeder kompetente Backend-Dev baut das in 4 Wochen nach.
- **On-Prem-Capability:** ja, aber kein einzigartiger Moat — DocuWare/ELO können das auch.
- **Solo-Founder-Velocity:** kein Moat, sondern ein Risiko (Bus-Faktor 1).
- **Marken/Vertrieb:** kein Moat, faktisch null.

**Verdikt:** Echter Moat = 1,5 (Backend-Tiefe in Spezial-Workflows). Reicht nicht für Massen-Markt, reicht für Boutique.

### 4. Go-to-Market (Kunde #2 nach Familien-Pilot)
**Realistische Pfade:**
- **Empfehlung über StB des Familienbetriebs** — wenn der StB überzeugt wird (DATEV-Export sauber, Belegbilder akzeptiert), wird er zu 1–2 anderen Mandanten weiterempfehlen. Wahrscheinlichkeit: 40%.
- **Cold Outreach an Anwaltskanzleien Solingen/NRW** mit On-Prem-USP. Sales-Cycle 6–9 Monate. Wahrscheinlichkeit pro Kontakt: <5%.
- **DATEV-Marketplace-Listung:** würde Vertrieb erschließen, aber Zertifizierung kostet Zeit + Geld + ist nicht heute machbar.
- **Community/Content:** Solo-Founder-Reichweite null. Unwahrscheinlich.

**Brutal:** Kunde #2 ist nicht in 4 Wochen drin. Plane 3–6 Monate.

### 5. Pricing
Empfehlung: **Perpetual License 8.000 € + 1.800 €/Jahr Maintenance** für 10-MA-Kunde. Bei Custom-Anpassung +5–15 k€ Projekt.
**Break-Even-CAC:** Bei 8.000 € Initial + 1.800 €/Jahr ergibt 5-Jahres-LTV ~17.000 €. CAC darf ~25% LTV = 4.250 € sein. Bei Solo-Founder-Sales (kein bezahlter Vertrieb) heißt das: ~5–8 Tage Sales-Aufwand pro Kunde maximal. Realistisch eher 15–20 Tage. **CAC-Defizit.**

### 6. Sales-Cycle
Deutsche KMU 5–30 MA Software-Beschaffung mit StB-Beteiligung: **3–9 Monate** Erstkontakt → Bestellung. Bei On-Prem-Hardware-Pflicht eher 6–9 Monate. Vergleichswerte: DocuWare/ELO publizieren 4–12 Monate, lexoffice/sevDesk Self-Service in Tagen.

### 7. Support
**Nicht skalierbar.** Solo-Founder + 32-Container-Stack + GPU-Box auf Kundenseite → bei 5 Kunden bist du 50% der Zeit Support, bei 10 Kunden 100%. Lösung: **Managed-On-Prem-Service** (Ben hostet 1 Kunde pro Tenant auf eigener Hardware) oder **Pivot zu SaaS** (Cloud-deployed) oder **Partner-Modell** (lokaler IT-Dienstleister tut First-Level). Heute: keiner dieser Pfade gangbar.

### 8. Scope-Bloat-Risk
**Klares Risiko, kein Asset.** 4-fache Codebase in 5 Monaten ohne Kunden = Feature-Fabrikation ohne Validation. Audit 00b zeigt überlappende Buckets (`workflow/`/`bpmn/`/`approval/`), 10 stub-Module, 56× `except Exception: pass`, 87 KB Logik in einem `__init__.py`. **Du baust schneller als du wegwirfst.** Empfehlung: **20% der Services entfernen vor Pilot.** Konkret: `ai_ethics/`, `ceo_dashboard/`, `knowledge_graph/`, `scanner/`, `templates/` vermutlich kandidaten. Plus: `workflow/`+`bpmn/`+`approval/` konsolidieren.

### 9. Red Team — wahrscheinlichster Failure-Mode in 12 Monaten
**Szenario:** Pilot beim Familienbetrieb läuft 4 Wochen ok. Bei Streckengeschäft-Edge-Case stürzt Backend-Container nachts ab. Ben fixt um 3 Uhr. Familienbetrieb beschwert sich beim StB. StB sagt: „Macht doch DATEV Online." Kunde springt ab. Ben hat keine Pipeline. Runway endet. **Wahrscheinlichkeit: 40%.**

Alternative: Ben bleibt 9 Monate an Code-Hardening (siehe Hardening-Welle in Ground-Truth §4) und baut keine zweite Kunden-Pipeline auf. Runway endet ohne Markt-Validation. **Wahrscheinlichkeit: 30%.**

### 10. Pivot-Optionen
- **Spin-Off „LkSG-Compliance-Suite"** — Lieferkettensorgfaltspflicht ist gesetzlicher Zwang ab 1.000 MA. Ablage-Compliance-Stack ist 70% wiederverwendbar. Markt zahlungskräftig. Erfolgsaussicht: **6/10**, aber Solo-Founder schafft das ohne Compliance-Sales-Erfahrung kaum.
- **Spin-Off „Procurement Cockpit"** (Eingangsrechnung-Verifikation als API-Service für ERPs). B2B2B-Modell, integriert in SAP/MS-Dynamics. Erfolgsaussicht: **5/10**, aber langer Sales-Cycle.
- **Spin-Off „Business Graph / RAG für eigene Akten"** — On-Prem-Chat über Geschäftsunterlagen. Markt formiert sich gerade. Erfolgsaussicht: **7/10**, aber Konkurrenz von OpenAI/MS Copilot wird hart.
- **Pivot „Family Office Light"** — UHNW-Patriarchen mit Privatvermögen + Geschäft + Familienakten. Boutique-Markt, aber zahlungsbereit. Erfolgsaussicht: **6/10**, am ehrlichsten zum existierenden Code (38 Privat-Services!).

**Top-Pivot:** Family-Office-Light + RAG-on-Prem-Bundle. Beides existiert im Code, beides hat Differenzierung.

### 11. Build-or-Bury Note
**5 von 10.**

Begründung: Code-Tiefe ist beeindruckend (Backend 8/10), aber Markt-Strategie ist unausgegoren (3/10), GTM ist ungeplant (2/10), Solo-Skalierung ist mathematisch unmöglich für KMU-Massen-Markt (1/10), Pivot-Optionen existieren aber sind unentschieden (5/10). Du wirst in 24 Monaten **nicht mit dem Produkt als KMU-Cloud-Alternative** leben. Du kannst mit einem **fokussierten Boutique-Produkt** leben, wenn du in 90 Tagen pivotierst.

---

## Empfehlung: Pilot machen ja/nein/wann

**JA — aber als Lern-Pilot, nicht als Vertriebs-Pilot.** In 4–6 Wochen, nicht 4 Wochen. Vorbedingungen:
1. JWT-httpOnly-Cookie-Fix (Audit 00h)
2. Verfahrensdokumentation persistiert (Audit 00i)
3. Live-Walk End-to-End mit hochgefahrenem System (Audit 00j hat das nicht geleistet)
4. 20% Scope-Reduktion (entkernen, nicht hinzufügen)
5. Glasklares Erfolgs-Kriterium definieren: „nach 8 Wochen entscheidet der StB des Familienbetriebs ob er das System weiterempfehlen würde". Das ist Kunde #2-Indikator.

**Wenn StB-Empfehlung negativ:** sofortige Pivot-Diskussion. Nicht „wir verbessern das Produkt".

---

## 3 Strategische Empfehlungen für die nächsten 4 Wochen

1. **ICP-Reframe und Landing-Page schreiben (Woche 1).** Nicht „Cloud-Alternative für KMU". Sondern: „On-Prem Document-Intelligence für datenschutz-kritische Mittelständler und Family Offices mit komplexen Sondergeschäften". Das ist ehrlicher und schließt 70% der Konkurrenz aus dem Pitch aus. Schreibe eine 1-Seite-USP, die du dem StB des Familienbetriebs vorlegen kannst.
2. **Steuerberater-Conversation in Woche 2 starten.** Den StB des Familienbetriebs **vor dem Pilot** ansprechen. Frage: „Was muss das System leisten, dass du es deinen anderen Mandanten empfiehlst?" Das ist Kunde-#2-Pipeline-Generation und gleichzeitig Compliance-Prio-Liste. Falls StB sagt „DATEV-Zertifizierung Pflicht" — entscheidende Information.
3. **Scope-Diät vor Pilot (Woche 3–4).** Entferne 5 Stub-Module (`ai_ethics/`, `ceo_dashboard/`, `knowledge_graph/`, `scanner/`, `templates/`), konsolidiere `workflow/`+`bpmn/`+`approval/` zu einem Modul, fixe die 56 `except Exception: pass`-Hotspots in Banking/Imports (Audit 00b §6) und den `asyncio.run()`-Bug in `adhoc_report_service.py:991`. Pilot startet mit kleinerer, robusterer Codebase. **Nichts Neues bauen vor Pilot.** Schreibstopp für 4 Wochen.

---

**Brutal-Schluss:** Du hast in 5 Monaten 600 Services geschrieben und 0 zahlende Kunden. Das Backend ist ein Kunstwerk. Das Geschäft existiert noch nicht. Wenn du in den nächsten 90 Tagen den ICP nicht schärfst und Kunde #2 nicht in der Pipeline hast, ist das mit 60% Wahrscheinlichkeit ein Hobby-Projekt mit Enterprise-Eindruck. Mit den richtigen drei Schritten oben ist es mit 40% Wahrscheinlichkeit ein Boutique-Geschäft, das dich in 24 Monaten ernährt. Beides ist möglich. Code allein entscheidet es nicht — Vertrieb tut es.
