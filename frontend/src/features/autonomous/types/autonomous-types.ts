/**
 * TypeScript types for Autonomous Trust System
 */

export type TrustLevelName = 'assistance' | 'auto_accept' | 'confidence' | 'autonomous';

export type ProposalType =
  | 'file_document'
  | 'approve_payment'
  | 'send_dunning'
  | 'update_master_data'
  | 'assign_entity'
  | 'classify_document';

export type ProposalStatus =
  | 'pending'
  | 'approved'
  | 'rejected'
  | 'auto_accepted'
  | 'expired'
  | 'rolled_back'
  | 'cancelled';

export interface TrustLevelResponse {
  level: number;
  level_name: TrustLevelName;
  is_enabled: boolean;
  immediate_threshold: number;
  delayed_threshold: number;
  delay_hours: number;
  require_confirmation: boolean;
  allow_auto_apply: boolean;
  document_type?: string;
}

export interface TrustMetricsResponse {
  total_decisions: number;
  auto_applied: number;
  approved: number;
  rejected: number;
  corrected: number;
  approval_rate: number;
  error_rate: number;
  avg_confidence: number;
  days_without_error: number;
  last_error_at?: string;
}

export interface TrustRecommendationResponse {
  current_level: number;
  recommended_level: number;
  reason: string;
  confidence: number;
  can_upgrade: boolean;
  upgrade_requirements: string[];
}

export interface PendingApprovalResponse {
  id: string;
  proposal_type: ProposalType;
  target_id: string;
  proposed_value: Record<string, unknown>;
  confidence: number;
  delay_hours: number;
  status: ProposalStatus;
  created_at: string;
  scheduled_at: string;
  reasoning?: string;
  time_remaining_hours?: number;
}

export interface ProposalHistoryResponse {
  id: string;
  proposal_type: ProposalType;
  target_id: string;
  proposed_value: Record<string, unknown>;
  confidence: number;
  status: ProposalStatus;
  created_at: string;
  executed_at?: string;
  approved_at?: string;
  rejected_at?: string;
  auto_accepted_at?: string;
  rolled_back_at?: string;
  rollback_until?: string;
  can_rollback: boolean;
  rejection_reason?: string;
  reasoning?: string;
}

export interface ProposalStatistics {
  period_days: number;
  total_proposals: number;
  by_status: Record<ProposalStatus, number>;
  by_type: Record<ProposalType, number>;
  avg_confidence: number;
  auto_acceptance_rate: number;
  approval_rate: number;
  rejection_rate: number;
  pending_count: number;
}

export interface UpdateTrustLevelRequest {
  level: number;
  document_type?: string;
  reason?: string;
}

export interface ApproveProposalResponse {
  success: boolean;
  message: string;
  status: ProposalStatus;
  can_rollback: boolean;
}

export interface RejectProposalRequest {
  reason?: string;
}

export interface RollbackProposalResponse {
  success: boolean;
  message: string;
  status: ProposalStatus;
}

export interface PendingApprovalsFilters {
  proposal_type?: ProposalType;
  limit?: number;
  offset?: number;
}

export interface ProposalHistoryFilters {
  target_id?: string;
  proposal_type?: ProposalType;
  status?: ProposalStatus;
  days?: number;
  limit?: number;
}
