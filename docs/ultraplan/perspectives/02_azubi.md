# 02 — Perspektive Azubi (1. Lehrjahr, 19, Excel-Schulpraktikum)

**Datum:** 2026-05-03
**Wer ich bin:** Azubi Buerokaufmann/-frau, 1. Lehrjahr. Excel im Schulpraktikum gelernt. "Buchungssatz" hab ich mal gehoert. SKR03 sagt mir nichts. Belege scannen ist neu fuer mich. Wenn was rot blinkt kriege ich Panik. Ich nutze TikTok mehr als Word.

---

## 1-Sentence-Verdict

Ich verstehe nicht, was 90% der Sidebar-Punkte sind, hab Angst auf "Loeschen" zu klicken weil ich nicht weiss ob das umkehrbar ist, und niemand erklaert mir was "SKR03" oder "Buchungssatz" heisst — ich brauche zwei Wochen Anleitung bevor ich hier was anfasse.

---

## Pflichtfragen

### 1. Onboarding-Flows: existieren die?

Ja, mehrfach. Sogar zu viel:

- `frontend/src/components/onboarding/WelcomeModal.tsx` — Modal mit 4 Schritten (Upload, OCR, Suche, Organisation), Storage-Key `ablage_onboarding_complete`. 4 Seiten Bilderbuch.
- `frontend/src/components/onboarding/CompanySetupWizard.tsx` + 4 Steps (`CompanyInfoStep`, `AccountingSettingsStep`, `UserInviteStep`, `CompletionStep`).
- `frontend/src/features/onboarding/components/OnboardingWizard.tsx` — **zweiter** Wizard (CompanySetup, Upload, Result, Complete, Welcome).
- `frontend/src/features/help/components/OnboardingTour.tsx` — **drittes** Onboarding.
- `frontend/src/features/product-tour/components/ProductTour.tsx` + `TourProvider.tsx` + `TourSpotlight.tsx` + `TourTooltip.tsx` + `TourLauncher.tsx` — **viertes** Onboarding-System.
- `frontend/src/features/product-tour/components/GettingStartedChecklist.tsx` (Sidebar-Footer Zeile 459 in `Sidebar.tsx`) — 8-Punkte-Checkliste.

Eine Welcome-/Onboarding-**Route** in `frontend/src/app/routes/`: **gibt es nicht** (`find frontend/src/app/routes -name "*welcome*"` liefert nichts).

**Problem:** Vier parallele Onboarding-Loesungen, alle in `localStorage`. Wenn ich am Tag 1 im Inkognito-Modus reinkomme oder mein Browser-Cache geleert wird, fang ich von vorne an. Und welche der vier Touren wird mir gezeigt? Wer entscheidet das?

### 2. Tooltips / Mikrocopy / In-App-Help

`grep -rn "Tooltip\|<Help" frontend/src/app/routes` -> **1 Treffer in 1 Route** von 299. (`admin.ocr-backends.$backend.tsx`).

Die Komponenten existieren (`ContextualTooltip.tsx`, `FeatureHint.tsx`, `HelpTooltip.tsx`, `HelpButton.tsx`, `HelpPanel.tsx`, `HelpSearch.tsx`, `HelpProvider.tsx`, `VideoPlayer.tsx`) — aber `grep -rln "ContextualTooltip\|HelpTooltip\|FeatureHint" frontend/src --include="*.tsx"` zeigt: **die Dateien werden nirgends importiert ausser sich selbst.** Das Tooltip-System ist gebaut und nicht verwendet.

Das `Tooltip`-Primitive wird in 29 Files importiert, **aber 0 davon sind Routes**. Heisst: Tooltips sind in tiefen Komponenten, nicht auf den Seiten wo ich als Azubi lande.

**Ich verstehe nicht** wofuer `KI-Pipeline`, `KI-Lernprofile`, `Trust Dashboard`, `Holding`, `Streckengeschaeft`, `Digitaler Zwilling` da sind — und nirgends erklaert es mir jemand mit einem `(?)`-Symbol.

### 3. Versehentlich Loeschen geklickt — Confirmation? Undo?

`grep -rln "AlertDialog\|ConfirmDialog" frontend/src --include="*.tsx" | wc -l` -> **89 Files**. Confirmation-Dialoge gibt es viele.

`grep -rln "Wiederherstellen\|wiederherstellen" frontend/src --include="*.tsx" | wc -l` -> **5 Files**. Undo/Restore: schwach. Es gibt einen Papierkorb (`frontend/src/app/routes/trash.tsx`) — wenigstens das.

**Problem fuer mich:** 89 Confirmation-Dialoge heisst, jede zweite Aktion fragt mich "Bist du sicher?". Das ist gut gegen Loeschen — aber bei 89 Dialogen ueberlies ich die irgendwann (Confirmation-Fatigue). Und ein **Undo-Toast** ("Geloescht — Rueckgaengig" wie Gmail) **gibt es nicht systemweit**, nur Papierkorb.

### 4. "Buchungssatz", "Skonto", "SKR03" — Glossar?

`grep -rln "Glossar\|glossary\|TermDefinition\|FachbegriffeHilfe" frontend/src` -> **0 Treffer**.

`SKR03/SKR04` taucht in 20+ Dateien auf (ConfigDialog, ValidationFelder, Datev-Utils) — **nirgends mit Erklaerungstext fuer Anfaenger**.

Es gibt eine `wissen.tsx`-Route (`frontend/src/app/routes/wissen.tsx`), aber das ist `KnowledgePage` fuer Notizen und Checklisten der User, **kein Glossar fuer Fachbegriffe**.

**Ich verstehe nicht** was passiert, wenn ich in `german-finance/ust` (USt-Voranmeldung) reinklicke. Das System sagt "Skonto", "Verzugszinsen", "BWA", "EUeR" — und ich frag mich: ist BWA eine Behoerde?

### 5. Sandbox / Uebungs-Modus?

`grep -rln "Sandbox\|sandbox\|Uebungs\|Demo-Modus\|playground" frontend/src` -> **3 Treffer**, alle entweder `LetterPreviewDialog` (Mahnungen-Vorschau, kein Sandbox), `DeveloperPortalPage` (API-Sandbox **fuer Entwickler**, nicht fuer mich), oder `useDeveloperPortal`.

`frontend/src/features/risk-scoring/examples/RiskScoringDemo.tsx` existiert — aber das ist ein internes Demo, nicht ueber die Sidebar erreichbar.

**Ich kann nirgends ueben ohne dass es echt wird.** Wenn ich heute eine echte Lieferantenrechnung scanne, geht die direkt in die echte Buchhaltung. Kein "Test-Mandant", kein "Sandbox-Modus". Keine "Beispiel-Daten zum Klicken". Wenn ich was kaputt mache, ist es kaputt.

### 6. Cognitive Load — Sidebar-Items zaehlen

`grep -c "<SidebarLink " frontend/src/components/layout/Sidebar.tsx` -> **108 SidebarLinks.**

Plus Submenues:
- "Berichte" Submenu (4 Items, Sidebar.tsx:131-137)
- "Finanzbuchhaltung" Submenu (3 Items, Sidebar.tsx:163-167)
- "Administration" Submenu (~50 Items, Sidebar.tsx:316-453, nur fuer Admin sichtbar)

Sektionen: Hauptmenue (oben), Berichte, Finanzbuchhaltung, **Ablage** (16 Items: Kunden, Lieferanten, Lieferanten-Ranking, Finanzen, Zahlungsverhalten, Auto-Zahlungen, PO-Matching, 3-Way-Matching, Abo-Rechnungen, Kassenbuch, Spesen, Streckengeschaeft, Personal, Vertraege, Vorlagen, Wissen, Privat, Lebenslagen), **Logistik** (2), **System** (4), Gespeicherte Suchen, Administration.

**Bewertung:** Fuer einen Azubi am Tag 1 ist das **erschlagend**. Das Microsoft Word-Menue hat ueberschaubare 9 Tabs. Hier sind 108+ direkte Links. Begriffe wie `KI-Autonomie`, `Smart Queue`, `Trust Dashboard`, `Knowledge-Graph`, `Steuerungszentrale`, `Digitaler Zwilling`, `Proaktiver Assistent` haben **keine Selbsterklaerung** und **keinen Hover-Tooltip** in der Sidebar.

Vergleich Lexoffice (Wettbewerber): ~7 Hauptmenuepunkte. Hier 108. Das Ratio ist **15x**.

---

## Cognitive-Load-Befund

| Metrik | Wert | Bewertung Azubi-Sicht |
|---|---|---|
| Sidebar-Links direkt | 108 | Ueberforderung |
| Versteckte Untermenues | 3 (Berichte, Finanzen, Admin) | Erst lernen, dass es sie gibt |
| Admin-Untermenue | ~50 weitere Items | Wenn ich Admin-Rechte kriege: Schock |
| Tooltips auf Routes | 1 von 299 | Praktisch null |
| Glossar | 0 | Fehlt komplett |
| Sandbox-Modus | 0 | Fehlt komplett |

**Fazit:** Das System hat **alle Funktionen die ein DAX-Konzern braucht**, in der Sidebar eines kleinen Familienbetriebs. Niemand hat fuer einen Anfaenger gefiltert was er an Tag 1 sehen soll.

---

## Was wuerde ich am ersten Tag falsch machen koennen?

1. **In "Mahnung-Automatik" reinklicken** (`/admin/automation/dunning`, Sidebar Zeile 348) und denken das ist ein Test-Knopf. Es ist die **Live-Mahnstrecke**. Eine Mahnung an einen wichtigen Kunden geht raus, weil ich auf "Ausfuehren" geklickt habe. Confirmation-Dialog wird vielleicht da sein, aber ich klicke "Ja" weil ich denke das ist ein Vorschau-Modus (siehe Punkt 5: Sandbox fehlt).

2. **In "Auto-Mahnlauf" -> Play-Button druecken** (`/banking/auto-mahnlauf`, Sidebar Zeile 372). Das Icon ist `Play` (Sidebar.tsx:372 importiert `Play` aus lucide-react). Ich denke "Play" wie YouTube-Play. Aber das ist "Mahnlauf starten". Geld wird gemahnt. Realistisch.

3. **Im Papierkorb auf "Endgueltig loeschen" klicken** anstatt "Wiederherstellen", weil ich nicht verstehe was die Begriffe bedeuten. Datei weg. Bei 5 Files mit `Wiederherstellen` ist die UX nicht systemweit konsistent.

4. **Beim Onboarding-Modal "Nicht mehr anzeigen" haken** (WelcomeModal.tsx:209-222), weil ich genervt bin, dass es die 3. Sidebar hintereinander ist. Dann sehe ich nie wieder die 8-Punkte-Checkliste-Erklaerung.

5. **In "Steuerungszentrale" / `command-center`** reinklicken (Sidebar Zeile 92) und denken das ist das Haupt-Dashboard. Es ist eine separate Power-User-Konsole. Ich verstehe die Buttons nicht, klicke wild rum, und triggere im schlimmsten Fall ein Workflow.

6. **DATEV-Export starten** (`/admin/datev`, Sidebar Zeile 113) und denken ich habe das Steuerberater-Paket gerade automatisch geschickt. In Wirklichkeit ist es ein Download. Aber ohne Erklaerung weiss ich das nicht.

---

## Top-3 Staerken (Azubi-UX-Sicht)

1. **Login + Forgot-Password sehen sauber aus** — laut Live-Walk-Report deutsche Texte, polished, mobile-tauglich. Erstkontakt mit dem System ist **nicht abschreckend**. (Quelle: 00j_LIVE_SYSTEM_REPORT.md §3.2 + §3.3.)

2. **Confirmation-Dialoge bei kritischen Aktionen** — 89 Files mit `AlertDialog`/`ConfirmDialog` heisst, dass Loeschungen meistens nachgefragt werden. Das rettet mich am Tag 1 oft. (Beispiel: `frontend/src/components/UnsavedChangesDialog.tsx` mit 24 Treffern, `features/admin/dlp/components/PolicyTable.tsx`, `features/admin/rules/components/RuleTable.tsx`.)

3. **Getting-Started-Checklist im Sidebar-Footer** (`features/product-tour/components/GettingStartedChecklist.tsx`) ist klein, sympathisch, hat klare 8 Schritte ("Dashboard ansehen", "Dokument hochladen", "Suche ausprobieren"). Wenn ich diese sehe und nicht direkt wegklicke, hilft sie.

---

## Top-3 Luecken (was Angst macht)

1. **Kein Glossar fuer "SKR03 / Buchungssatz / Skonto / BWA / EUeR / USt-Voranmeldung / Verzugszinsen / GoBD"** — diese Woerter stehen ueberall im UI (`features/datev/utils/validation.ts`, `features/german-finance/pages/BWAPage.tsx`, etc.) ohne ein einziges `(?)`-Tooltip. Ich google jeden Begriff in einem zweiten Tab. Das ist lehrlingsfeindlich.

2. **Kein Sandbox/Test-Modus** — keine "Beispieldaten klicken um zu lernen"-Option. Keine Demo-Mandanten-Trennung. Wenn ich uebe, ist es **echt**. Ich hab Angst und klicke deshalb gar nichts.

3. **108 Sidebar-Items + 4 parallele Onboardings + 1 Tooltip auf 299 Routes** — die Lernkurve ist nicht abgestuft. Ich brauche eine "Junior-Sicht" mit 8 Items (Upload, Suchen, Rechnungen, Kunden, Lieferanten, Hilfe, Profil) und alles andere sollte sich mit Zeit/Rolle freischalten. Stattdessen sehe ich am Tag 1 alles gleichzeitig — ohne Tooltip-Erklaerungen — und blockiere.

---

## Note "Azubi-Tauglichkeit"

**4 / 10**

Begruendung: Login + Welcome-Modal + Getting-Started-Checklist sind freundliche Erstberuehrung (+2). Confirmation-Dialoge fangen viele Loesch-Fehler ab (+1). Aber 108 Sidebar-Items ohne Tooltips, kein Glossar fuer 20+ Fachbegriffe, kein Sandbox-Modus, vier konkurrierende Onboarding-Systeme (`WelcomeModal`, `CompanySetupWizard`, `OnboardingWizard`, `OnboardingTour`/`ProductTour`), und Buttons wie "Auto-Mahnlauf -> Play" die im Live-Modus echte Mahnungen verschicken — das macht das System fuer einen 19-jaehrigen Anfaenger im 1. Lehrjahr **gefaehrlich**. Ich brauche in der Realitaet eine Senior-Buchhalterin neben mir, die mir 2 Wochen ueber die Schulter schaut. Das System ersetzt nicht — es **ueberfordert**.

Wenn ein Glossar (1 Tag Arbeit), Sidebar-Rollenfilter "Junior-Modus" (3 Tage), und ein Sandbox-Mandant (1 Woche) existieren wuerden, koennte die Note auf 7-8/10 springen. Die Bausteine sind da (`HelpProvider`, `HelpPanel`, `ContextualTooltip`) — sie werden nur nirgends benutzt.
