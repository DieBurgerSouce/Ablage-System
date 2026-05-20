import { apiClient } from '@/lib/api/client';

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

export async function getMyApprovals(status?: string): Promise<ApprovalListResponse> {
  const params: Record<string, string> = { assigned_to_me: 'true' };
  if (status && status !== 'all') params.status = status;
  const response = await apiClient.get<ApprovalListResponse>('/approvals', { params });
  return response.data;
}

export async function getApprovalDetail(id: string): Promise<ApprovalRequest> {
  const response = await apiClient.get<ApprovalRequest>(`/approvals/${id}`);
  return response.data;
}

export async function voteOnApproval(
  id: string,
  decision: 'approved' | 'rejected',
  comment?: string
): Promise<void> {
  await apiClient.post(`/approvals/${id}/vote`, { decision, comment });
}
