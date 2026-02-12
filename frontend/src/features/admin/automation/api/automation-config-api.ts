import { apiClient } from '@/lib/api/client'

// Dunning Config Types
export interface DunningConfig {
  reminder_after_days: number
  first_dunning_after_days: number
  second_dunning_after_days: number
  final_dunning_after_days: number
  first_dunning_fee: number
  second_dunning_fee: number
  final_dunning_fee: number
  late_interest_rate: number
  min_dunning_amount: number
  auto_process_enabled: boolean
  dry_run_mode: boolean
}

export interface DunningStats {
  active_dunnings_total: number
  by_level: Record<string, number>
  total_fees_collected: number
  total_outstanding_fees: number
  avg_resolution_days: number
}

// Autonomy Config Types
export interface TrustLevelConfig {
  action_type: string
  trust_level: 'immediate' | 'delayed' | 'confirm'
  confidence_threshold: number
}

export interface AutonomyConfig {
  document_classification_threshold: number
  entity_linking_threshold: number
  invoice_approval_threshold: number
  payment_matching_threshold: number
  ocr_correction_threshold: number
  payment_auto_approve_limit: number
  payment_suggest_limit: number
  dunning_auto_send_level: number
  dunning_min_overdue_days: number
  master_data_auto_update_confidence: number
  filing_auto_confidence: number
  filing_suggest_confidence: number
  action_trust_levels: TrustLevelConfig[]
}

// Queue Types
export interface QueuedAction {
  id: string
  action_type: string
  entity_name: string | null
  entity_type: string | null
  confidence: number
  reason: string
  proposed_change: string
  created_at: string | null
  will_execute_at: string | null
  status: string
}

// API Functions
export async function getDunningConfig(): Promise<DunningConfig> {
  const res = await apiClient.get<DunningConfig>('/admin/automation/dunning/config')
  return res.data
}

export async function updateDunningConfig(config: Partial<DunningConfig>): Promise<DunningConfig> {
  const res = await apiClient.put<DunningConfig>('/admin/automation/dunning/config', config)
  return res.data
}

export async function getDunningStats(): Promise<DunningStats> {
  const res = await apiClient.get<DunningStats>('/admin/automation/dunning/stats')
  return res.data
}

export async function getAutonomyConfig(): Promise<AutonomyConfig> {
  const res = await apiClient.get<AutonomyConfig>('/admin/automation/autonomy/config')
  return res.data
}

export async function updateAutonomyConfig(config: Partial<AutonomyConfig>): Promise<AutonomyConfig> {
  const res = await apiClient.put<AutonomyConfig>('/admin/automation/autonomy/config', config)
  return res.data
}

export async function getActionQueue(status: string = 'pending'): Promise<{ actions: QueuedAction[]; total: number }> {
  const res = await apiClient.get('/admin/automation/autonomy/queue', { params: { status } })
  return res.data
}

export async function approveAction(actionId: string): Promise<void> {
  await apiClient.post(`/admin/automation/autonomy/queue/${actionId}/approve`)
}

export async function rejectAction(actionId: string, reason?: string): Promise<void> {
  await apiClient.post(`/admin/automation/autonomy/queue/${actionId}/reject`, null, { params: { reason } })
}
