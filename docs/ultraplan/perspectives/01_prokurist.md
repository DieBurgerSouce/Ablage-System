# 01 — Prokurist (Solingen, 52, 18 Jahre Bürochef)

**Verdict in einem Satz:** Hochglanz-Schaufenster, dahinter ein Maschinenraum mit 3.012 API-Endpoints, der mir am Pilot-Tag in 30 % der Fälle das Genick brechen wird, wenn nicht jemand die Frontend-Lücken zuklappt und das Backend hochfährt.

---

## Workflow-Walk: "Eingangsrechnung scannen → buchen → archivieren"

So sieht der Klick-Pfad aus, den ich Montag früh um acht laufen muss. Ich zähle mit.

| # | Schritt | Was passiert | Datei:Zeile |
|---|---------|--------------|-------------|
| 1 | Login | `/login` mit E-Mail + Passwort, danach 2FA-Code | `frontend/src/app/routes/login.tsx`, `frontend/src/components/auth/TwoFactorInput.tsx` |
| 2 | Dashboard sehen | Admin-Dashboard rendert `DashboardGridEnhanced`, Header sagt "Guten Morgen" | `frontend/src/components/dashboard/AdminDashboardView.tsx:42-54` |
| 3 | Klick auf "Neuer Beleg" | Navigiert zu `/upload` | `AdminDashboardView.tsx:50-53` |
| 4 | Drag-Drop einer PDF-Rechnung | Frontend ruft `documentsService.upload()` mit `multipart/form-data` | `frontend/src/features/upload/components/UploadWizard.tsx:105-113`, `frontend/src/lib/api/services/documents.ts:203-224` |
| 5 | Backend nimmt entgegen | `POST /api/v1/documents/` validiert Dateiname, Magic-Bytes, Größe, schiebt in MinIO, erzeugt Celery-Task für OCR | `app/api/v1/documents.py:188-307` |
| 6 | Frontend pollt 2-Sekunden-Takt auf OCR-Status | Status `processing` → `awaiting_confirmation` → `completed` | `UploadWizard.tsx:773-917` |
| 7 | Klick "Eingangsrechnung" zur Bestätigung | `POST /documents/{id}/confirm-classification` setzt Tag | `app/api/v1/documents.py:2815-2904` |
| 8 | Optional: Rename-Vorschlag bestätigen | `POST /documents/{id}/confirm-rename` | `app/api/v1/documents.py:2920+` |
| 9 | Buchen? | **Hier wird's diffus.** Es gibt keinen Button "Buchen" am Beleg. Buchung passiert über `/admin/datev-connect/buchungen` oder über automatische Kontierung im Hintergrund | `frontend/src/app/routes/admin.datev-connect.buchungen.tsx`, `frontend/src/features/datev/components/connect/` |
| 10 | Archivieren | Passiert implizit. Dokument liegt nach Upload + Tag in der DB. "Archivieren" als bewusster Akt existiert nicht im Frontend-Tree |  Implizit über `Document.archived_at` |

**Brutale Wahrheit:** Der Flow "Eingangsrechnung → buchen → archivieren" ist als zusammenhängender Pfad **nirgends im Frontend abgebildet**. Upload-Seite, Smart Inbox, DATEV-Connect und Dokumenten-Liste sind vier verschiedene Welten. Es gibt keinen Daumennagel "Beleg → fertig in einem Rutsch". Mein Azubi muss vier Routes auswendig lernen.

---

## Friction-Points (konkret, nicht romantisiert)

1. **Upload-Polling alle 2 Sekunden** (`UploadWizard.tsx:911`). Bei 30 Belegen am Montag macht das Frontend ~15 API-Calls pro Sekunde. Auf einem Pilot-Server mit Nebel-Internet im Bergischen ein Garant für Frust.
2. **Keine Bulk-Klassifizierung.** Jeden Beleg muss ich einzeln per Dropdown als "Eingangsrechnung" bestätigen (`UploadWizard.tsx:210-259`). Bei 30 Belegen sind das 30 Dropdowns + 30 Bestätigungen = 60 Klicks.
3. **Kein "Buchen"-Button im Inbox.** Smart Inbox (`/inbox`) zeigt 5 Komponenten (`InboxItemCard`, `InboxFilters`, `InboxInsightsPanel`, `InboxStatsBar`, `InboxEmptyState`) — aber **keine direkte Buchungs-Aktion**. Der Beleg landet "irgendwo".
4. **HelpButton ist tot.** Existiert als Komponente in `frontend/src/features/help/components/HelpButton.tsx:18-72`, aber **wird in `__root.tsx` nie gemountet**. Der Bot/KI-Chat-FAB sitzt am gleichen Platz `bottom-6 right-6` (`__root.tsx:117-127`). Die Hilfe ist da, aber unauffindbar.
5. **Backend war beim Live-Walk offline.** Frontend-Pre-Fetch zu `GET /api/v1/documents/?per_page=4` schlägt mit 502 fehl, bevor ich überhaupt eingeloggt bin (`00j_LIVE_SYSTEM_REPORT.md:108-116`). Erster UX-Eindruck: "Server nicht erreichbar"-Toast. Macht Vertrauen kaputt.
6. **Umlaut-Bug "Zuruck zur Anmeldung"** auf `/forgot-password` (`00j_LIVE_SYSTEM_REPORT.md:77-94`). Bei einem System, das Umlauten zum Verkaufsargument macht, ist das wie wenn der Friseur mit ungewaschenen Haaren rumläuft.
7. **3.012 API-Endpoints, davon 554 in `orchestration.py` allein** (`00d_API_INVENTORY.md:36, 193`). Wenn das jemand warten muss, der nicht der Original-Coder ist — gute Nacht.
8. **`299 Routen / 127 Features`** (`00e_FRONTEND_AUDIT.md:31`). Selbst der Frontend-Engineer findet sich da nicht zurecht. Ich als Anwender erst recht nicht.

---

## 7 Pflichtfragen — direkt beantwortet

### 1. Kann ich Montag um 8:00 die Eingangspost (30 Belege) in <60 Min verarbeiten?

**Nein, mit Einschränkung.** Der Upload selbst (Drag-Drop) klappt. ABER: Pro Beleg muss ich Direction bestätigen + Rename bestätigen = 2 manuelle Klicks. Bei 30 Belegen = 60 Klicks zusätzlich zum Upload. Plus OCR-Wartezeit (2 s GPU laut README). Wenn auch nur einer hängt (`status: 'failed'`, `UploadWizard.tsx:891-896`) muss ich neu hochladen. Realistisch: 90–120 Minuten beim ersten Mal, 60 Min nach Übung. **Buchen** ist im selben Flow gar nicht enthalten — das ist ein zweiter Termin in `/admin/datev-connect/buchungen`. Der Trace zeigt: Frontend `UploadWizard.tsx` → API `documents.py:188` → Service `storage_service` + Celery → DB `Document`-Tabelle. Sauber gebaut, aber **nicht für Stoßbetrieb**.

### 2. Steuerberaterin ruft an "Q3-Belege schicken" — wie viele Klicks?

**Mit Einschränkung machbar.** Es gibt `/tax-package` (`frontend/src/app/routes/tax-package.tsx`) und einen `TaxPackagePage`-Komponente. Plus DATEV-Export unter `/admin/datev/export` mit Datum-Picker "Von/Bis" + Konfigurations-Auswahl (`ExportPage.tsx:172-202`). Geschätzt 5–8 Klicks: Sidebar → Tax-Package → Quartal wählen → Export → Download → E-Mail. **Aber:** Wenn keine DATEV-Konfiguration angelegt ist, schickt mich das System auf eine Setup-Seite mit "Keine Konfiguration vorhanden" (`ExportPage.tsx:90-113`). Erst-Setup verlangt Beraternummer + Mandantennummer — die ich dann erstmal von der Steuerberaterin holen muss. **Note: Mit-Einschränkung.**

### 3. Bei Tippfehler: verständliche Fehlermeldung oder 500er?

**Ja.** Die Backend-API liefert 97 explizite `detail=`-Strings auf Deutsch in `documents.py` (z.B. `"Dateityp nicht erlaubt"`, `"Datei zu groß"`, `"Leere Datei"`, `app/api/v1/documents.py:233-273`). HTTPExceptions mit Status 400/413, nicht 500. Das Frontend zeigt diese im Toast (`UploadWizard.tsx:133-140`). Bei Backend-Down kommt sauber "Server nicht erreichbar" statt White Screen (`00j_LIVE_SYSTEM_REPORT.md:46-52`). **Note: Ja.** Das ist eine der wenigen Stellen, wo das System wirklich gut ist.

### 4. Hilfe-Button — existiert? Was steht dahinter?

**Mit Einschränkung — nein, in der Praxis.** Komponente existiert (`frontend/src/features/help/components/HelpButton.tsx:18-72`), zeigt einen FAB unten rechts mit Tooltip "Hilfe & Anleitungen" und einem Badge bei neuen Inhalten. Dahinter ein `HelpPanel` mit Video-Tutorials und Onboarding-Status. **Aber:** `grep -rn "HelpButton" frontend/src` findet exakt einen Treffer — die Definition selbst. **Wird nirgends gemountet.** Im `__root.tsx` sitzt stattdessen ein `KiChatFab` an der gleichen Position. Heißt: Die Hilfe ist gebaut, getestet, deutsch — und der Pilot-User wird sie nicht finden. **Note: Nein.**

### 5. Wenn Internet aus: kann ich noch arbeiten?

**Mit Einschränkung — Lesen ja, Schreiben halbwegs.** Ein `OfflineQueue`-Store existiert (`frontend/src/stores/offline-queue.ts`) mit Mutation-Queue, Sync-Status, Init-Hook. Eingebaut wird er in `__root.tsx` als `OfflineSyncStatusBar` und `OfflineIndicator`. PWA mit Service-Worker und Caching-Strategien (NetworkFirst für API, CacheFirst für Docs) ist aktiv (`00e_FRONTEND_AUDIT.md:35`). **ABER:** Beim Live-Walk wurde nicht verifiziert ob der Offline-Modus wirklich funktioniert. OCR braucht GPU, Buchen braucht DATEV-Sync — das sind Online-Operationen. Realistisch: Liste anschauen ja, neuen Beleg verarbeiten nein. **Note: Mit-Einschränkung.**

### 6. "WARTE, falsch gebucht" — gibt's Undo?

**Ja, technisch.** Globaler `UndoProvider` ist in `__root.tsx:87` aktiv mit `maxStackSize: 30, toastDuration: 6000`. `useUndoableAction.tsx:34-47` definiert sauberen Stack mit `execute`/`undo`-Callbacks. Wird konkret genutzt z.B. in `RecentActionsPanel.tsx:93-110` für KI-Aktionen ("Rueckgaengig"-Button mit Undo2-Icon). **ABER:** Der Undo-Toast hat 6 Sekunden Lebensdauer. Wenn ich einmal weggeklickt habe — weg. Und für die GoBD-relevanten Buchungen (DATEV-Export, Hash-Chain) gibt's keinen Undo, das wäre auch falsch. Für UI-Aktionen (Tag setzen, Rename) ja, für Geld-Operationen nein. **Note: Ja, mit der nötigen Einschränkung.**

### 7. Erste 10 Sekunden nach Login: verstehe ich, was ich tun soll?

**Mit Einschränkung — ja, wenn ich Admin bin.** `AdminDashboardView` zeigt: Begrüßung mit Namen + Datum, "Neuer Beleg"-Button rechts oben, "Weiter wo Sie aufgehört haben"-Komponente, dann ein Widget-Grid (`AdminDashboardView.tsx:35-64`). Standard-Preset enthält `today`, `system-status`, `finance-status`, `quick-links`, `upload`, `recent-documents` (`useDashboardStore.ts:62-70`). Klare Aufgabe ablesbar: "Beleg hochladen" oder "Letzte Dokumente". **Aber:** Kein Tutorial-Overlay beim ersten Login (Onboarding-Wizard ist im `localStorage`, also nur einmal — `00j_LIVE_SYSTEM_REPORT.md:74`). Wenn ich das Browser wechsle oder Inkognito-Modus benutze, kommt der Wizard wieder. Der Erst-Eindruck ist gut. Der Zweit-Eindruck verwirrt. **Note: Ja-mit-Einschränkung.**

---

## Top-3 Stärken

1. **Backend-Down-Toast statt White Screen.** Das Frontend zeigt deutsche Fehler-Toasts wenn die API 502 wirft, kein endloser Skeleton-Loader (`00j_LIVE_SYSTEM_REPORT.md:46-52`). Das ist erwachsene Arbeit.
2. **Visual Polish + deutsche Sprache durchgehend.** 17 `: any`-Treffer auf 127 Features — FAANG-Niveau (`00e_FRONTEND_AUDIT.md:32`). 97 deutsche Error-Detail-Strings in `documents.py`. Login-Page sieht nicht generisch-AI aus.
3. **2FA, Password-Reset, Onboarding-Wizard, 404-Page sind da und funktionieren.** 5 von 6 FAANG-Pilot-Blocker behoben, mit Tests (`00e_FRONTEND_AUDIT.md:13-21`). Damit ist das Frontend für einen 1-Kunden-Pilot **objektiv** bereit.

---

## Top-3 Lücken

1. **Kein zusammenhängender Workflow "Beleg → buchen → archivieren".** Vier verschiedene Routes, vier verschiedene mentale Modelle. Ein Bürochef will EINEN Knopf, nicht vier Tabs. Smart Inbox (`/inbox`) hat keine Buchungs-Aktion, DATEV-Connect ist eine separate Welt, Archivieren existiert nur als Datenbank-Feld. **Pilot-Blocker.**
2. **HelpButton existiert, wird nicht gemountet.** Wenn der Pilot-User Hilfe braucht und sie ist gebaut aber unsichtbar, ist das ärgerlicher als wenn sie nicht da wäre. Ein `grep` fand exakt eine Stelle: die Definition. **5-Minuten-Fix.**
3. **3.012 Endpoints, 299 Routen, 554 Endpoints in einem einzigen `orchestration.py`** (`00d_API_INVENTORY.md:36, 193`). Das ist ein Wartungs-Albtraum. Der Pilot kann fliegen, aber wenn ein Bug auftaucht, sucht der Entwickler eine Woche. Refactor vor Skalierung > 3 Kunden.

---

## Note für Pilot-User-Tauglichkeit: **5 / 10**

| Dimension | Punkte |
|-----------|--------|
| Technisch da | 8/10 — Backend liefert, Frontend ist polished, Auth komplett |
| Workflow-Verständlichkeit | 3/10 — Belege-zu-Buchung als zusammenhängender Pfad fehlt |
| Erstkontakt-UX | 6/10 — Dashboard klar, aber Pre-Fetch-502 macht ersten Eindruck kaputt |
| Robustheit | 5/10 — Backend war beim Audit-Walk offline, Umlaut-Bug auf öffentlicher Seite |
| Hilfe & Recovery | 4/10 — HelpButton tot, Undo nur 6 Sekunden, kein "Beleg falsch hochgeladen — fix" |
| Pilot-Skalierbarkeit | 3/10 — Bei 3 Kunden muss `orchestration.py` zerlegt werden |

**Bottom line:** Wenn ich am Montag morgen den Pilot starte und das Backend läuft sauber, schaffe ich die 30 Belege in 90 Minuten. Wenn das Backend hustet — und beim Audit hat es gehustet — sitze ich bis zum Mittag. Für einen einzelnen Pilot-Kunden mit Hand-Holding durch Ben: machbar. Für "verkauft, geht raus, Kunde wird allein gelassen": **nein, noch nicht**.

---

## Eine direkte Frage an Ben

**Ben, hast Du Dir den Eingangsrechnungs-Workflow EINMAL als zusammenhängenden Pfad live geklickt — von Drag-Drop bis "Buchung in DATEV gelandet" — oder hast Du nur die einzelnen Bausteine gebaut und gehofft, dass der Prokurist sie zusammenstöpselt? Wenn ja: zeig mir das Video. Wenn nein: bau dem Inbox einen "Buchen & archivieren"-Button, bevor Du den Pilot startest.**
