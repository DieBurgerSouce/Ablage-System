/**
 * Delegation Management API
 *
 * API functions for delegation operations
 */

import { apiClient } from '@/lib/api';
import type {
  Delegation,
  DelegationCreateRequest,
  DelegationUpdateRequest,
  DelegationListResponse,
  DelegationResponse,
  DelegationTemplateListResponse,
  DelegationAuditLogResponse,
  DelegationFilters,
} from './types';

const DELEGATIONS_BASE_URL = '/delegations';

/**
 * Get list of delegations (given and received)
 */
export async function getDelegations(
  filters?: DelegationFilters,
  page: number = 1,
  pageSize: number = 20
): Promise<DelegationListResponse> {
  const params = new URLSearchParams();
  params.set('page', String(page));
  params.set('page_size', String(pageSize));

  if (filters?.status) {
    params.set('status', filters.status);
  }
  if (filters?.direction) {
    params.set('direction', filters.direction);
  }
  if (filters?.active_only !== undefined) {
    params.set('active_only', String(filters.active_only));
  }

  const response = await apiClient.get<DelegationListResponse>(
    `${DELEGATIONS_BASE_URL}?${params.toString()}`
  );
  return response.data;
}

/**
 * Get a specific delegation by ID
 */
export async function getDelegation(delegationId: string): Promise<Delegation> {
  const response = await apiClient.get<DelegationResponse>(
    `${DELEGATIONS_BASE_URL}/${delegationId}`
  );
  return response.data.delegation;
}

/**
 * Create a new delegation
 */
export async function createDelegation(
  request: DelegationCreateRequest
): Promise<DelegationResponse> {
  const response = await apiClient.post<DelegationResponse>(
    DELEGATIONS_BASE_URL,
    request
  );
  return response.data;
}

/**
 * Update an existing delegation
 */
export async function updateDelegation(
  delegationId: string,
  request: DelegationUpdateRequest
): Promise<DelegationResponse> {
  const response = await apiClient.patch<DelegationResponse>(
    `${DELEGATIONS_BASE_URL}/${delegationId}`,
    request
  );
  return response.data;
}

/**
 * Accept a pending delegation (as delegate)
 */
export async function acceptDelegation(
  delegationId: string
): Promise<DelegationResponse> {
  const response = await apiClient.post<DelegationResponse>(
    `${DELEGATIONS_BASE_URL}/${delegationId}/accept`
  );
  return response.data;
}

/**
 * Decline a pending delegation (as delegate)
 */
export async function declineDelegation(
  delegationId: string,
  reason?: string
): Promise<DelegationResponse> {
  const response = await apiClient.post<DelegationResponse>(
    `${DELEGATIONS_BASE_URL}/${delegationId}/decline`,
    { reason }
  );
  return response.data;
}

/**
 * Revoke an active delegation (as delegator)
 */
export async function revokeDelegation(
  delegationId: string,
  reason?: string
): Promise<DelegationResponse> {
  const response = await apiClient.post<DelegationResponse>(
    `${DELEGATIONS_BASE_URL}/${delegationId}/revoke`,
    { reason }
  );
  return response.data;
}

/**
 * Extend a delegation's end date
 */
export async function extendDelegation(
  delegationId: string,
  newEndDate: string
): Promise<DelegationResponse> {
  const response = await apiClient.post<DelegationResponse>(
    `${DELEGATIONS_BASE_URL}/${delegationId}/extend`,
    { new_end_date: newEndDate }
  );
  return response.data;
}

/**
 * Get delegation templates
 */
export async function getDelegationTemplates(): Promise<DelegationTemplateListResponse> {
  const response = await apiClient.get<DelegationTemplateListResponse>(
    `${DELEGATIONS_BASE_URL}/templates`
  );
  return response.data;
}

/**
 * Get audit log for a delegation
 */
export async function getDelegationAuditLog(
  delegationId: string,
  limit: number = 50
): Promise<DelegationAuditLogResponse> {
  const response = await apiClient.get<DelegationAuditLogResponse>(
    `${DELEGATIONS_BASE_URL}/${delegationId}/audit-log?limit=${limit}`
  );
  return response.data;
}

/**
 * Search for users to delegate to
 */
export async function searchDelegateUsers(
  query: string,
  limit: number = 10
): Promise<{ users: Array<{ id: string; email: string; display_name?: string }> }> {
  const response = await apiClient.get<{ users: Array<{ id: string; email: string; display_name?: string }> }>(
    `/users/search?q=${encodeURIComponent(query)}&limit=${limit}`
  );
  return response.data;
}
