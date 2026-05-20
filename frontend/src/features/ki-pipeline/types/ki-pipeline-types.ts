/**
 * KI-Pipeline Types
 * German enterprise document processing - AI intelligence layer
 */

// ============= Backend Types =============

export interface FieldConfidence {
  field: string;
  confidence: number; // 0.0 to 1.0
  extracted_value: string | number | null;
  source: 'deepseek' | 'got-ocr' | 'surya' | 'tesseract' | 'manual';
}

export interface LearningProfile {
  entity_type: 'supplier' | 'customer' | 'document_type';
  entity_id: string; // UUID or document_type name
  entity_name: string;
  accuracy_overall: number; // 0.0 to 1.0
  accuracy_per_field: Record<string, number>;
  samples_count: number;
  last_trained: string | null; // ISO timestamp
}

export interface CrossDocumentMatch {
  document_id: string;
  document_type: 'Bestellung' | 'Lieferschein' | 'Rechnung';
  match_type: 'order_to_delivery' | 'delivery_to_invoice' | 'order_to_invoice';
  confidence: number;
  matched_fields: string[];
  created_at: string;
}

export interface DocumentSummary {
  document_id: string;
  summary_text: string;
  key_facts: string[];
  language: 'de' | 'en';
  generated_at: string;
}

export interface PriceDeviation {
  document_id: string;
  document_number: string | null;
  field: string;
  expected_value: number;
  actual_value: number;
  deviation_percent: number;
  supplier_name: string | null;
  created_at: string;
}

export interface CorrectionInput {
  field: string;
  original_value: string | number | null;
  corrected_value: string | number | null;
}

export interface LearnFromCorrectionsRequest {
  document_id: string;
  corrections: CorrectionInput[];
}

export interface ExtractWithConfidenceRequest {
  document_id: string;
}

export interface ExtractWithConfidenceResponse {
  document_id: string;
  fields: FieldConfidence[];
  overall_confidence: number;
}

export interface KIPipelineStatistics {
  total_documents_processed: number;
  avg_confidence_score: number;
  learning_profiles_count: number;
  recent_corrections_count: number;
  high_confidence_fields_percent: number;
}

export interface FieldAccuracyStats {
  field: string;
  accuracy: number;
  sample_count: number;
  last_updated: string | null;
}

export interface SupplierAccuracyStats {
  entity_id: string;
  entity_name: string;
  overall_accuracy: number;
  field_accuracies: Record<string, number>;
  total_documents: number;
}

// ============= Frontend Types =============

export interface ConfidenceLevel {
  label: string;
  color: 'green' | 'yellow' | 'red';
  min: number;
  max: number;
}

export const CONFIDENCE_LEVELS: Record<string, ConfidenceLevel> = {
  high: { label: 'Hoch', color: 'green', min: 0.9, max: 1.0 },
  medium: { label: 'Mittel', color: 'yellow', min: 0.6, max: 0.9 },
  low: { label: 'Niedrig', color: 'red', min: 0.0, max: 0.6 },
};

export function getConfidenceLevel(confidence: number): ConfidenceLevel {
  if (confidence >= 0.9) return CONFIDENCE_LEVELS.high;
  if (confidence >= 0.6) return CONFIDENCE_LEVELS.medium;
  return CONFIDENCE_LEVELS.low;
}

// ============= Transform Functions =============

export function transformFieldConfidence(data: FieldConfidence): FieldConfidence {
  return {
    ...data,
    confidence: Math.max(0, Math.min(1, data.confidence)),
  };
}

export function transformLearningProfile(data: LearningProfile): LearningProfile {
  return {
    ...data,
    accuracy_overall: Math.max(0, Math.min(1, data.accuracy_overall)),
    accuracy_per_field: Object.fromEntries(
      Object.entries(data.accuracy_per_field).map(([k, v]) => [
        k,
        Math.max(0, Math.min(1, v)),
      ])
    ),
  };
}

export function transformCrossDocumentMatch(
  data: CrossDocumentMatch
): CrossDocumentMatch {
  return {
    ...data,
    confidence: Math.max(0, Math.min(1, data.confidence)),
  };
}

// ============= UI Labels =============

export const FIELD_LABELS: Record<string, string> = {
  // Kopfdaten
  document_number: 'Belegnummer',
  document_date: 'Belegdatum',
  supplier_name: 'Lieferant',
  customer_name: 'Kunde',
  delivery_date: 'Lieferdatum',
  order_number: 'Bestellnummer',

  // Summen
  total_gross: 'Bruttosumme',
  total_net: 'Nettosumme',
  tax_amount: 'Steuerbetrag',
  tax_rate: 'Steuersatz',

  // Positionen
  position_number: 'Position',
  article_number: 'Artikelnummer',
  description: 'Beschreibung',
  quantity: 'Menge',
  unit_price: 'Einzelpreis',
  line_total: 'Zeilensumme',

  // Zahlungsbedingungen
  payment_terms: 'Zahlungsbedingungen',
  due_date: 'Fälligkeitsdatum',
  bank_account: 'Bankverbindung',
  iban: 'IBAN',
  bic: 'BIC',
};

export const ENTITY_TYPE_LABELS: Record<string, string> = {
  supplier: 'Lieferant',
  customer: 'Kunde',
  document_type: 'Dokumenttyp',
};

export const DOCUMENT_TYPE_LABELS: Record<string, string> = {
  Bestellung: 'Bestellung',
  Lieferschein: 'Lieferschein',
  Rechnung: 'Rechnung',
};

export const MATCH_TYPE_LABELS: Record<string, string> = {
  order_to_delivery: 'Bestellung → Lieferschein',
  delivery_to_invoice: 'Lieferschein → Rechnung',
  order_to_invoice: 'Bestellung → Rechnung',
};

export const SOURCE_LABELS: Record<string, string> = {
  deepseek: 'DeepSeek-Janus',
  'got-ocr': 'GOT-OCR 2.0',
  surya: 'Surya',
  tesseract: 'Tesseract',
  manual: 'Manuell',
};
