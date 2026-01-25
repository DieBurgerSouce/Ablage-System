/**
 * Consent Management API
 *
 * DSGVO Art. 6, 7 - Einwilligungsverwaltung API Calls
 */

import { api } from '@/lib/api';
import type {
  ConsentStatusResponse,
  ConsentGrantRequest,
  ConsentGrantResponse,
  ConsentWithdrawResponse,
  ConsentHistoryResponse,
  ConsentScope,
} from './types';

const CONSENT_BASE_URL = '/api/v1/users/me/gdpr/consent';

/**
 * Ruft den aktuellen Einwilligungs-Status ab
 */
export async function getConsentStatus(): Promise<ConsentStatusResponse> {
  const response = await api.get<ConsentStatusResponse>(CONSENT_BASE_URL);
  return response.data;
}

/**
 * Erteilt oder aktualisiert eine Einwilligung
 */
export async function grantConsent(
  request: ConsentGrantRequest
): Promise<ConsentGrantResponse> {
  const response = await api.post<ConsentGrantResponse>(CONSENT_BASE_URL, request);
  return response.data;
}

/**
 * Widerruft eine Einwilligung
 */
export async function withdrawConsent(
  scope: ConsentScope,
  reason?: string
): Promise<ConsentWithdrawResponse> {
  const params = new URLSearchParams();
  if (reason) {
    params.set('reason', reason);
  }
  const queryString = params.toString();
  const url = `${CONSENT_BASE_URL}/${scope}${queryString ? `?${queryString}` : ''}`;
  const response = await api.delete<ConsentWithdrawResponse>(url);
  return response.data;
}

/**
 * Ruft die Einwilligungs-Historie ab
 */
export async function getConsentHistory(
  scope?: ConsentScope,
  limit: number = 50
): Promise<ConsentHistoryResponse> {
  const params = new URLSearchParams();
  if (scope) {
    params.set('scope', scope);
  }
  params.set('limit', limit.toString());
  const response = await api.get<ConsentHistoryResponse>(
    `${CONSENT_BASE_URL}/history?${params.toString()}`
  );
  return response.data;
}
