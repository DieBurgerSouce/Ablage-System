/**
 * Document Comparison Types
 *
 * TypeScript-Typen fuer die Dokumentenvergleich-Funktion.
 */

export type ComparisonType = 'text' | 'structured' | 'visual' | 'hybrid';
export type DifferenceType = 'added' | 'removed' | 'changed' | 'unchanged';
export type FieldCategory = 'identifier' | 'amount' | 'date' | 'entity' | 'address' | 'text' | 'metadata';

export interface TextDifference {
  type: DifferenceType;
  positionStart: number;
  positionEnd: number;
  originalText: string;
  newText: string;
  contextBefore: string;
  contextAfter: string;
}

export interface FieldChange {
  fieldName: string;
  category: FieldCategory;
  oldValue: unknown;
  newValue: unknown;
  changeType: DifferenceType;
  significance: 'critical' | 'high' | 'medium' | 'low';
}

export interface ComparisonResult {
  documentId1: string;
  documentId2: string;
  comparisonType: ComparisonType;
  similarityScore: number;
  textSimilarity: number;
  structureSimilarity: number;
  textDifferences: TextDifference[];
  fieldChanges: FieldChange[];
  summary: string;
  comparedAt: string;
}

export interface DocumentInfo {
  id: string;
  filename: string;
  documentType: string | null;
  createdAt: string | null;
}

export interface DiffReport {
  document1Info: DocumentInfo;
  document2Info: DocumentInfo;
  comparisonResult: ComparisonResult;
  detailedChanges: Record<string, unknown>[];
  visualDiffAvailable: boolean;
  recommendations: string[];
  generatedAt: string;
}

export interface SimilarDocument {
  documentId: string;
  filename: string;
  documentType: string | null;
  similarityScore: number;
  matchingFields: string[];
  uploadDate: string;
}

export interface CompareDocumentsRequest {
  documentId1: string;
  documentId2: string;
  comparisonType?: ComparisonType;
}

// Labels fuer UI
export const COMPARISON_TYPE_LABELS: Record<ComparisonType, string> = {
  text: 'Textvergleich',
  structured: 'Strukturvergleich',
  visual: 'Visueller Vergleich',
  hybrid: 'Kombinierter Vergleich',
};

export const DIFFERENCE_TYPE_LABELS: Record<DifferenceType, string> = {
  added: 'Hinzugefuegt',
  removed: 'Entfernt',
  changed: 'Geaendert',
  unchanged: 'Unveraendert',
};

export const FIELD_CATEGORY_LABELS: Record<FieldCategory, string> = {
  identifier: 'Identifikator',
  amount: 'Betrag',
  date: 'Datum',
  entity: 'Unternehmen/Person',
  address: 'Adresse',
  text: 'Freitext',
  metadata: 'Metadaten',
};

export const SIGNIFICANCE_LABELS: Record<string, string> = {
  critical: 'Kritisch',
  high: 'Hoch',
  medium: 'Mittel',
  low: 'Niedrig',
};
