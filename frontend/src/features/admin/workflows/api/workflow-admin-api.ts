/**
 * Workflow Admin API Client
 *
 * API-Client für Approval-Management und Workflow-Analytics.
 */

import { apiClient } from '@/lib/api/client';

// =============================================================================
// Types
// =============================================================================

export interface ApprovalStep {
  step_number: number;
  role: string;
  approver_name: string | null;
  approver_id: string | null;
  decision: 'approved' | 'rejected' | 'pending' | null;
  decided_at: string | null;
  comment: string | null;
  required: boolean;
  sla_hours: number | null;
}

export interface ApprovalRequest {
  id: string;
  document_id: string;
  document_name: string;
  document_type: string;
  workflow_id: string;
  workflow_name: string;
  current_step: number;
  total_steps: number;
  status: 'pending' | 'approved' | 'rejected' | 'expired';
  created_at: string;
  updated_at: string;
  sla_deadline: string | null;
  approval_chain: ApprovalStep[];
  requester_name: string;
  amount: number | null;
}

export interface ApprovalListResponse {
  items: ApprovalRequest[];
  total: number;
}

export interface ApprovalListParams {
  status?: string;
  workflow_id?: string;
  date_from?: string;
  date_to?: string;
  offset?: number;
  limit?: number;
}

export interface VotePayload {
  decision: 'approved' | 'rejected';
  comment?: string;
}

// =============================================================================
// API Functions
// =============================================================================

/**
 * Listet Approval-Requests mit optionalen Filtern.
 */
export async function listApprovals(params: ApprovalListParams = {}): Promise<ApprovalListResponse> {
  const response = await apiClient.get<ApprovalListResponse>('/approvals', { params });
  return response.data;
}

/**
 * Ruft ein Approval-Request Detail ab.
 */
export async function getApprovalDetail(id: string): Promise<ApprovalRequest> {
  const response = await apiClient.get<ApprovalRequest>(`/approvals/${id}`);
  return response.data;
}

/**
 * Stimmt über ein Approval-Request ab.
 */
export async function voteOnApproval(id: string, payload: VotePayload): Promise<void> {
  await apiClient.post(`/approvals/${id}/vote`, payload);
}

/**
 * Ruft Workflow-Analytics ab.
 */
export async function getWorkflowAnalytics(): Promise<Record<string, unknown>> {
  const response = await apiClient.get('/workflow_analytics');
  return response.data;
}
