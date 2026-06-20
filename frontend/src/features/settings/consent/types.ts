/**
 * Consent Management Types
 *
 * DSGVO Art. 6, 7 - Einwilligungsverwaltung
 */

export const ConsentScope = {
  PERSONAL_DATA: 'personal_data',
  FINANCIAL_DATA: 'financial_data',
  DOCUMENT_PROCESSING: 'document_processing',
  ANALYTICS: 'analytics',
  MARKETING: 'marketing',
  THIRD_PARTY_SHARING: 'third_party_sharing',
  AUTOMATED_DECISIONS: 'automated_decisions',
} as const;
export type ConsentScope = (typeof ConsentScope)[keyof typeof ConsentScope];

export interface ConsentScopeInfo {
  scope: ConsentScope;
  scope_description: string;
  consent_given: boolean;
  consent_version: string | null;
  granted_at: string | null;
  valid_until: string | null;
}

export interface ConsentStatusResponse {
  user_id: string;
  scopes: ConsentScopeInfo[];
  total_consents: number;
  active_consents: number;
  nachricht: string;
}

export interface ConsentGrantRequest {
  scope: ConsentScope;
  consent_given: boolean;
  valid_until?: string | null;
}

export interface ConsentGrantResponse {
  success: boolean;
  consent_id: string;
  scope: string;
  consent_given: boolean;
  consent_version: string | null;
  granted_at: string;
  nachricht: string;
}

export interface ConsentWithdrawResponse {
  success: boolean;
  scope: string;
  withdrawn_at: string;
  consent_id: string;
  nachricht: string;
}

export interface ConsentHistoryEntry {
  id: string;
  action: string;
  scope: string;
  previous_value: boolean | null;
  new_value: boolean;
  consent_version: string | null;
  ip_address: string | null;
  reason: string | null;
  created_at: string;
}

export interface ConsentHistoryResponse {
  user_id: string;
  history: ConsentHistoryEntry[];
  total: number;
}

// Lokalisierte Beschreibungen für die UI
export const CONSENT_SCOPE_LABELS: Record<ConsentScope, string> = {
  [ConsentScope.PERSONAL_DATA]: 'Persönliche Daten',
  [ConsentScope.FINANCIAL_DATA]: 'Finanzdaten',
  [ConsentScope.DOCUMENT_PROCESSING]: 'Dokumentenverarbeitung',
  [ConsentScope.ANALYTICS]: 'Analyse & Statistiken',
  [ConsentScope.MARKETING]: 'Marketing',
  [ConsentScope.THIRD_PARTY_SHARING]: 'Weitergabe an Dritte',
  [ConsentScope.AUTOMATED_DECISIONS]: 'Automatisierte Entscheidungen',
};

export const CONSENT_SCOPE_DESCRIPTIONS: Record<ConsentScope, string> = {
  [ConsentScope.PERSONAL_DATA]:
    'Verarbeitung Ihrer personenbezogenen Daten wie Name, E-Mail und Kontaktinformationen.',
  [ConsentScope.FINANCIAL_DATA]:
    'Verarbeitung Ihrer Finanzdaten wie Kontoinformationen und Transaktionen.',
  [ConsentScope.DOCUMENT_PROCESSING]:
    'OCR-Verarbeitung und automatische Texterkennung Ihrer Dokumente.',
  [ConsentScope.ANALYTICS]:
    'Erstellung von Statistiken und Analysen zur Verbesserung unserer Dienste.',
  [ConsentScope.MARKETING]:
    'Zusendung von Marketing-Mitteilungen und Produktinformationen.',
  [ConsentScope.THIRD_PARTY_SHARING]:
    'Weitergabe Ihrer Daten an ausgewählte Drittanbieter.',
  [ConsentScope.AUTOMATED_DECISIONS]:
    'Automatisierte Entscheidungsfindung basierend auf Ihren Daten.',
};

// Icons für die Scopes
export const CONSENT_SCOPE_ICONS: Record<ConsentScope, string> = {
  [ConsentScope.PERSONAL_DATA]: 'User',
  [ConsentScope.FINANCIAL_DATA]: 'Landmark',
  [ConsentScope.DOCUMENT_PROCESSING]: 'FileText',
  [ConsentScope.ANALYTICS]: 'BarChart3',
  [ConsentScope.MARKETING]: 'Mail',
  [ConsentScope.THIRD_PARTY_SHARING]: 'Share2',
  [ConsentScope.AUTOMATED_DECISIONS]: 'Bot',
};
