/**
 * Document Quality Types
 *
 * TypeScript-Interfaces für die Datenqualitäts-Ampel.
 * Entspricht den Backend-Modellen in app/api/v1/document_quality.py.
 */

// =============================================================================
// Ampel Color
// =============================================================================

/** Ampel-Farbe: gruen, gelb oder rot */
export type AmpelColor = 'gruen' | 'gelb' | 'rot';

// =============================================================================
// Document Quality
// =============================================================================

/** Einzelne Qualitätsdimension mit Score und Gewichtung */
export interface QualityDimension {
  /** Name der Dimension (z.B. "OCR-Konfidenz") */
  name: string;
  /** Score von 0.0 bis 1.0 */
  score: number;
  /** Gewichtung der Dimension (0.0 - 1.0) */
  weight: number;
  /** Beschreibung der Dimension */
  details: string;
  /** Unter-Scores als Key-Value-Paare */
  sub_scores: Record<string, number>;
}

/** Qualitätsbewertung eines einzelnen Dokuments */
export interface DocumentQualityResponse {
  /** Dokument-ID */
  document_id: string;
  /** Composite Score von 0.0 bis 1.0 */
  score: number;
  /** Ampel-Farbe */
  ampel_color: AmpelColor;
  /** Beschreibung des Ampel-Status */
  ampel_label: string;
  /** Einzelne Qualitätsdimensionen */
  dimensions: QualityDimension[];
  /** Verbesserungsempfehlungen */
  recommendations: string[];
}

// =============================================================================
// Company Quality Overview
// =============================================================================

/** Einzelne Ampel-Kategorie mit Anzahl und Prozent */
export interface AmpelKategorie {
  /** Anzahl Dokumente in dieser Kategorie */
  anzahl: number;
  /** Prozentualer Anteil (0.0 - 100.0) */
  prozent: number;
}

/** Ampel-Verteilung über alle Dokumente */
export interface AmpelVerteilung {
  /** Gute Qualität (Score >= 0.80) */
  gruen: AmpelKategorie;
  /** Mittlere Qualität (Score 0.50 - 0.79) */
  gelb: AmpelKategorie;
  /** Schlechte Qualität (Score < 0.50) */
  rot: AmpelKategorie;
}

/** Unternehmensweite Qualitätsübersicht */
export interface CompanyQualityOverviewResponse {
  /** Gesamtanzahl bewerteter Dokumente */
  total_documents: number;
  /** Durchschnittlicher Qualitäts-Score (0.0 - 1.0) */
  average_score: number;
  /** Ampel-Verteilung */
  verteilung: AmpelVerteilung;
}
