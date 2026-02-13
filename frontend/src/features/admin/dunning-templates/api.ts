/**
 * Dunning Templates API
 * API-Funktionen für Mahnbrief-Vorlagen und PDF-Generierung
 */

import { api } from '@/lib/api';
import type {
  DunningTemplate,
  DunningRecord,
  InterestRates,
  LetterPreviewParams,
  BatchGenerateParams,
} from './types';

const API_BASE = '/api/v1/banking/dunning';

/**
 * Offene Mahnvorgaenge abrufen
 */
export async function getDunningRecords(params?: {
  status?: string;
  level?: number;
  limit?: number;
}): Promise<DunningRecord[]> {
  const response = await api.get(API_BASE, {
    params: {
      status: params?.status ?? 'active',
      dunning_level: params?.level,
      limit: params?.limit ?? 50,
    },
  });
  const data = response.data;
  const items = data.items || data.records || data || [];
  return Array.isArray(items)
    ? items.map((item: Record<string, unknown>) => ({
        id: String(item.id ?? ''),
        documentId: String(item.document_id ?? ''),
        invoiceNumber: String(item.invoice_number ?? item.belegnummer ?? ''),
        entityName: String(item.entity_name ?? item.counterparty_name ?? ''),
        amount: Number(item.amount ?? item.total_amount ?? 0),
        daysOverdue: Number(item.days_overdue ?? 0),
        currentLevel: Number(item.current_level ?? item.level ?? 1),
        status: String(item.status ?? 'pending'),
        lastActionAt: item.last_action_at ? String(item.last_action_at) : null,
      }))
    : [];
}

/**
 * Verfügbare Mahnbrief-Vorlagen abrufen
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
 * Aktuelle Verzugszinssätze abrufen
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
