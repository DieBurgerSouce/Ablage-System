/**
 * Correction Workbench Types
 * Typen fuer OCR-Korrektur-Workbench
 */

export interface LowConfidenceDocument {
  id: string;
  documentId: string;
  filename: string;
  documentType: string | null;
  backendUsed: string;
  overallConfidence: number;
  extractedText: string;
  thumbnailUrl?: string;
  createdAt: string;
  fields: LowConfidenceField[];
}

export interface LowConfidenceField {
  fieldName: string;
  value: string;
  confidence: number;
  correctedValue?: string;
  correctionType?: string;
}

export interface CorrectionSubmission {
  documentId: string;
  fieldName: string;
  originalValue: string;
  correctedValue: string;
  correctionType: 'umlaut' | 'date' | 'amount' | 'name' | 'iban' | 'general';
  backendUsed: string;
  notes?: string;
}

export interface CorrectionStats {
  totalCorrections: number;
  correctionsToday: number;
  correctionsThisWeek: number;
  pendingReview: number;
  byType: Record<string, number>;
  byBackend: Record<string, number>;
  topContributors: Array<{
    userId: string;
    userName: string;
    correctionCount: number;
  }>;
}

export interface TrainingExportConfig {
  format: 'deepseek_jsonl' | 'surya_hf' | 'generic_jsonl' | 'csv';
  splitRatio: {
    train: number;
    val: number;
    test: number;
  };
  splitStrategy: 'random' | 'stratified' | 'temporal';
  verifiedOnly: boolean;
  minUmlautAccuracy: number;
  includeMetadata: boolean;
}

export interface TrainingExportResult {
  success: boolean;
  exportId: string;
  outputDir: string;
  format: string;
  stats: {
    totalSamples: number;
    trainSamples: number;
    valSamples: number;
    testSamples: number;
    samplesWithUmlauts: number;
    avgTextLength: number;
    documentTypes: Record<string, number>;
    exportTimeSeconds: number;
    outputSizeBytes: number;
  };
  filesCreated: string[];
  errors: string[];
  warnings: string[];
}

export interface QueueFilters {
  maxConfidence: number;
  backend: string | null;
  documentType: string | null;
  hasUmlauts: boolean | null;
}

export type CorrectionType = 'umlaut' | 'date' | 'amount' | 'name' | 'iban' | 'general';

export const CORRECTION_TYPE_LABELS: Record<CorrectionType, string> = {
  umlaut: 'Umlaut-Fehler',
  date: 'Datumsfehler',
  amount: 'Betragsfehler',
  name: 'Namensfehler',
  iban: 'IBAN-Fehler',
  general: 'Allgemein',
};

export const CORRECTION_TYPE_DESCRIPTIONS: Record<CorrectionType, string> = {
  umlaut: 'ae, oe, ue, ss Fehler',
  date: 'Falsch erkanntes Datum',
  amount: 'Zahlen/Waehrung falsch',
  name: 'Namen falsch erkannt',
  iban: 'IBAN/Bankdaten falsch',
  general: 'Sonstige Fehler',
};
