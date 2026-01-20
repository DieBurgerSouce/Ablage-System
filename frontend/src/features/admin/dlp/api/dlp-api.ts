/**
 * DLP (Data Loss Prevention) API Client
 *
 * Verwaltet DLP-Policies, Zugriffskontrollen und Sensitive-Data-Scanning.
 */

import apiClient from '@/lib/api/client';

// ==================== Types ====================

export type DLPAction = 'allow' | 'block' | 'watermark' | 'notify' | 'audit_only';

export type SensitiveDataType =
  | 'credit_card'
  | 'iban'
  | 'ssn'
  | 'email'
  | 'phone'
  | 'tax_id'
  | 'date_of_birth'
  | 'health_data'
  | 'financial_data';

export interface DLPPolicy {
  id: string;
  name: string;
  description?: string;
  enabled: boolean;
  allowed_roles: string[];
  blocked_roles: string[];
  time_restrictions?: {
    start_hour?: number;
    end_hour?: number;
    allowed_days?: number[];
  };
  document_types: string[];
  tags_required: string[];
  tags_blocked: string[];
  action: DLPAction;
  require_watermark: boolean;
  watermark_config?: {
    text?: string;
    position?: 'top_left' | 'top_right' | 'bottom_left' | 'bottom_right' | 'center' | 'diagonal';
    opacity?: number;
    font_size?: number;
    include_username?: boolean;
    include_timestamp?: boolean;
    include_document_id?: boolean;
  };
  notify_admin: boolean;
  notify_user: boolean;
  log_access: boolean;
}

export interface PolicyCreateRequest {
  id: string;
  name: string;
  description?: string;
  enabled?: boolean;
  allowed_roles?: string[];
  blocked_roles?: string[];
  time_restrictions?: DLPPolicy['time_restrictions'];
  document_types?: string[];
  tags_required?: string[];
  tags_blocked?: string[];
  action?: DLPAction;
  require_watermark?: boolean;
  watermark_config?: DLPPolicy['watermark_config'];
  notify_admin?: boolean;
  notify_user?: boolean;
  log_access?: boolean;
}

export interface PolicyUpdateRequest {
  name?: string;
  description?: string;
  enabled?: boolean;
  allowed_roles?: string[];
  blocked_roles?: string[];
  time_restrictions?: DLPPolicy['time_restrictions'];
  document_types?: string[];
  tags_required?: string[];
  tags_blocked?: string[];
  action?: DLPAction;
  require_watermark?: boolean;
  watermark_config?: DLPPolicy['watermark_config'];
  notify_admin?: boolean;
  notify_user?: boolean;
  log_access?: boolean;
}

export interface PolicyListResponse {
  policies: DLPPolicy[];
  total: number;
}

export interface DLPCheckResult {
  allowed: boolean;
  action: DLPAction;
  policy_id?: string;
  reason?: string;
  watermark_required: boolean;
  watermark_config?: DLPPolicy['watermark_config'];
}

export interface ScanRequest {
  text: string;
  types?: SensitiveDataType[];
}

export interface ScanResponse {
  has_sensitive_data: boolean;
  findings: Partial<Record<SensitiveDataType, number>>;
  summary: string;
}

export interface AccessCheckRequest {
  document_id: string;
  action_type: 'download' | 'view' | 'print' | 'export';
}

// ==================== API Functions ====================

/**
 * Alle DLP-Policies auflisten (Admin)
 */
export async function listPolicies(): Promise<PolicyListResponse> {
  const response = await apiClient.get<PolicyListResponse>('/dlp/policies');
  return response.data;
}

/**
 * Neue Policy erstellen (Admin)
 */
export async function createPolicy(data: PolicyCreateRequest): Promise<DLPPolicy> {
  const response = await apiClient.post<DLPPolicy>('/dlp/policies', data);
  return response.data;
}

/**
 * Policy abrufen (Admin)
 */
export async function getPolicy(policyId: string): Promise<DLPPolicy> {
  const response = await apiClient.get<DLPPolicy>(`/dlp/policies/${policyId}`);
  return response.data;
}

/**
 * Policy aktualisieren (Admin)
 */
export async function updatePolicy(
  policyId: string,
  data: PolicyUpdateRequest
): Promise<DLPPolicy> {
  const response = await apiClient.patch<DLPPolicy>(`/dlp/policies/${policyId}`, data);
  return response.data;
}

/**
 * Policy loeschen (Admin)
 */
export async function deletePolicy(policyId: string): Promise<void> {
  await apiClient.delete(`/dlp/policies/${policyId}`);
}

/**
 * Zugriffspruefung durchfuehren
 */
export async function checkAccess(data: AccessCheckRequest): Promise<DLPCheckResult> {
  const response = await apiClient.post<DLPCheckResult>('/dlp/check', data);
  return response.data;
}

/**
 * Text auf sensible Daten scannen
 */
export async function scanSensitiveData(data: ScanRequest): Promise<ScanResponse> {
  const response = await apiClient.post<ScanResponse>('/dlp/scan', data);
  return response.data;
}

/**
 * Verfuegbare Typen sensibler Daten abrufen
 */
export async function getSensitiveDataTypes(): Promise<string[]> {
  const response = await apiClient.get<string[]>('/dlp/sensitive-data-types');
  return response.data;
}

// ==================== Export ====================

export const dlpApi = {
  listPolicies,
  createPolicy,
  getPolicy,
  updatePolicy,
  deletePolicy,
  checkAccess,
  scanSensitiveData,
  getSensitiveDataTypes,
};
