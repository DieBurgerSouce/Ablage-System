/**
 * Kontextuelle Hilfe-Tooltips
 *
 * Zentrale Definition aller HelpTooltip-Texte.
 * Werden im Einsteiger-Modus neben den jeweiligen UI-Elementen angezeigt.
 * Alle Texte in Deutsch.
 */

export const HELP_TOOLTIPS = {
  ocr_confidence:
    'Die Konfidenz zeigt, wie sicher das System bei der Texterkennung ist. Gruene Werte (>95%) sind zuverlaessig, gelbe (70-95%) sollten geprueft werden, rote (<70%) muessen korrigiert werden.',

  backend_selector:
    'Das OCR-Backend bestimmt, welche KI den Text erkennt. "Auto" waehlt automatisch das beste Backend basierend auf dem Dokumenttyp.',

  document_direction:
    'Eingangsrechnung = Rechnung an Sie (Lieferantenrechnung). Ausgangsrechnung = Rechnung von Ihnen an einen Kunden.',

  entity_linking:
    'Verknuepfen Sie Dokumente mit Lieferanten oder Kunden fuer automatische Zuordnung bei zukuenftigen Dokumenten. Das System lernt aus jeder Verknuepfung.',

  self_learning:
    'Das System lernt aus Ihren Korrekturen. Je mehr Sie korrigieren, desto besser wird die Erkennung fuer aehnliche Dokumente.',

  search_mode:
    'Volltext: Sucht exakte Woerter. Semantisch: Versteht Bedeutungen und findet aehnliche Konzepte. Hybrid: Kombiniert beide Methoden fuer beste Ergebnisse.',

  batch_upload:
    'Laden Sie mehrere Dokumente gleichzeitig hoch. Alle werden parallel verarbeitet. Der Fortschritt wird in Echtzeit angezeigt.',

  risk_score:
    'Der Risiko-Score bewertet Geschaeftspartner basierend auf Zahlungsverhalten, offenen Posten und Vertragshistorie. Hohe Werte bedeuten hoehere Risiken.',

  skonto:
    'Skonto ist ein Preisnachlass bei schneller Zahlung. Das System trackt Skonto-Fristen automatisch und warnt vor Ablauf.',

  document_chain:
    'Dokumentenketten verbinden zusammengehoerige Belege: Angebot, Bestellung, Lieferschein, Rechnung. Das System erkennt Ketten automatisch.',

  approval_workflow:
    'Genehmigungsworkflows bestimmen, wer welche Rechnungen freigeben darf. Regeln basieren auf Betrag, Lieferant und Kategorie.',

  datev_export:
    'DATEV-Export erzeugt Buchungssaetze im DATEV-Format (CSV/XML) inklusive Belegbildern. Kompatibel mit DATEV Unternehmen Online.',

  gdpr_retention:
    'Aufbewahrungsfristen werden automatisch ueberwacht. Nach Ablauf werden Dokumente zur Loeschung vorgeschlagen (DSGVO-konform).',

  confidence_threshold:
    'Der Konfidenz-Schwellenwert bestimmt, ab welchem Wert OCR-Ergebnisse automatisch akzeptiert werden. Niedrigere Werte erfordern mehr manuelle Pruefung.',

  digital_twin:
    'Der Digitale Zwilling zeigt eine 360-Grad-Sicht auf Ihr Unternehmen: Finanzen, Risiken, Compliance und Geschaeftsbeziehungen auf einen Blick.',
} as const

export type HelpTooltipKey = keyof typeof HELP_TOOLTIPS
