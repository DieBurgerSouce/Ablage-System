/**
 * Dunning Templates API
 * API-Funktionen fuer Mahnbrief-Vorlagen und PDF-Generierung
 */

import { api } from '@/lib/api';
import type {
  DunningTemplate,
  InterestRates,
  LetterPreviewParams,
  BatchGenerateParams,
} from './types';

const API_BASE = '/api/v1/banking/dunning';

/**
 * Verfuegbare Mahnbrief-Vorlagen abrufen
 */
export async function getLetterTemplates(): Promise<DunningTemplate[]> {
  const response = await api.get(`${API_BASE}/letter-templates`);
  const data = response.data;

  return (data || []).map((item: Record<string, unknown>) => ({
    level: Number(item.level || 0),
    name: String(item.name || ''),
    title: String(item.title || ''),
    tone: String(item.tone || 'sachlich'),
    fee: Number(item.fee || 0),
    paymentDays: Number(item.payment_days || 14),
    escalationWarning: item.escalation_warning ? String(item.escalation_warning) : null,
    templateFile: String(item.template_file || ''),
  }));
}

/**
 * Aktuelle Verzugszinssaetze abrufen
 */
export async function getInterestRates(): Promise<InterestRates> {
  const response = await api.get(`${API_BASE}/interest-rates`);
  const data = response.data;

  return {
    baseRate: Number(data.base_rate || 0),
    b2bRate: Number(data.b2b_rate || 0),
    b2cRate: Number(data.b2c_rate || 0),
    legalBasis: String(data.legal_basis || 'BGB §288'),
    b2bPauschale: Number(data.b2b_pauschale || 40),
    b2bPauschaleLegalBasis: String(data.b2b_pauschale_legal_basis || 'BGB §288 Abs. 5'),
    note: String(data.note || ''),
  };
}

/**
 * HTML-Vorschau eines Mahnbriefs abrufen
 */
export async function getLetterPreview(params: LetterPreviewParams): Promise<string> {
  const queryParams = new URLSearchParams({
    dunning_level: String(params.dunningLevel),
    is_b2b: String(params.isB2b),
  });

  const response = await api.get(
    `${API_BASE}/${params.dunningId}/letter/preview?${queryParams}`,
    { responseType: 'text' }
  );

  return response.data;
}

/**
 * Mahnbrief als PDF herunterladen
 */
export async function downloadLetterPdf(params: LetterPreviewParams): Promise<Blob> {
  const queryParams = new URLSearchParams({
    dunning_level: String(params.dunningLevel),
    is_b2b: String(params.isB2b),
  });

  const response = await api.get(
    `${API_BASE}/${params.dunningId}/letter/pdf?${queryParams}`,
    { responseType: 'blob' }
  );

  return response.data;
}

/**
 * Mehrere Mahnbriefe als ZIP herunterladen
 */
export async function downloadBatchLetters(params: BatchGenerateParams): Promise<Blob> {
  const queryParams = new URLSearchParams({
    dunning_level: String(params.dunningLevel),
    is_b2b: String(params.isB2b),
  });

  // IDs als separate Parameter
  params.dunningIds.forEach((id) => {
    queryParams.append('dunning_ids', id);
  });

  const response = await api.post(
    `${API_BASE}/letters/batch?${queryParams}`,
    {},
    { responseType: 'blob' }
  );

  return response.data;
}
