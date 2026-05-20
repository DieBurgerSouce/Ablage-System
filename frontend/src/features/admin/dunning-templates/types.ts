/**
 * Dunning Templates Types
 * Typen für Mahnbrief-Vorlagen und PDF-Generierung
 */

export interface DunningTemplate {
  level: number;
  name: string;
  title: string;
  tone: 'freundlich' | 'sachlich' | 'bestimmt' | 'streng';
  fee: number;
  paymentDays: number;
  escalationWarning: string | null;
  templateFile: string;
}

export interface InterestRates {
  baseRate: number;
  b2bRate: number;
  b2cRate: number;
  legalBasis: string;
  b2bPauschale: number;
  b2bPauschaleLegalBasis: string;
  note: string;
}

export interface DunningRecord {
  id: string;
  documentId: string;
  invoiceNumber: string;
  entityName: string;
  amount: number;
  daysOverdue: number;
  currentLevel: number;
  status: string;
  lastActionAt: string | null;
}

export interface LetterPreviewParams {
  dunningId: string;
  dunningLevel: number;
  isB2b: boolean;
}

export interface BatchGenerateParams {
  dunningIds: string[];
  dunningLevel: number;
  isB2b: boolean;
}
