/**
 * Invoice Workflow API Client - Vollautomatischer Rechnungsworkflow
 *
 * API-Funktionen für automatische Rechnungsverarbeitung und Freigabe-Pipeline.
 * Unterstützt Zero-Touch-Automation mit intelligenter Freigabe.
 *
 * Backend-Endpunkte:
 * - GET /api/v1/zero-touch/pipeline - Pipeline-Status
 * - GET /api/v1/zero-touch/queue - Freigabe-Warteschlange
 * - POST /api/v1/zero-touch/approve/{id} - Rechnung genehmigen
 * - POST /api/v1/zero-touch/reject/{id} - Rechnung ablehnen
 * - GET /api/v1/zero-touch/stats - Automatisierungsstatistiken
 */

import { apiClient } from '@/lib/api/client';

// ==================== Types ====================

export interface PipelineStage {
  name: string;
  status: 'pending' | 'processing' | 'completed' | 'error';
  count: number;
}

export interface PipelineStatus {
  stages: PipelineStage[];
  total_processed: number;
  auto_approved: number;
  pending_review: number;
}

export interface ApprovalItem {
  id: string;
  document_id: string;
  document_title: string;
  supplier_name: string;
  amount: number;
  currency: string;
  confidence: number;
  suggested_action: string;
  reason: string;
  created_at: string;
}

export interface ApprovalQueue {
  items: ApprovalItem[];
  total: number;
}

export interface AutomationStats {
  total_processed: number;
  auto_approved: number;
  auto_rejected: number;
  manual_review: number;
  approval_rate: number;
  avg_processing_time_seconds: number;
}

export interface ApproveRejectResponse {
  success: boolean;
  message: string;
}

// ==================== Query Keys ====================

export const invoiceWorkflowKeys = {
  all: ['invoice-workflow'] as const,
  pipeline: () => [...invoiceWorkflowKeys.all, 'pipeline'] as const,
  queue: () => [...invoiceWorkflowKeys.all, 'queue'] as const,
  stats: () => [...invoiceWorkflowKeys.all, 'stats'] as const,
};

// ==================== API Functions ====================

/**
 * Holt den aktuellen Pipeline-Status
 */
export async function getPipelineStatus(): Promise<PipelineStatus> {
  const response = await apiClient.get<PipelineStatus>('/zero-touch/pipeline');
  return response.data;
}

/**
 * Holt die Freigabe-Warteschlange
 */
export async function getApprovalQueue(): Promise<ApprovalQueue> {
  const response = await apiClient.get<ApprovalQueue>('/zero-touch/queue');
  return response.data;
}

/**
 * Holt die Automatisierungsstatistiken
 */
export async function getAutomationStats(): Promise<AutomationStats> {
  const response = await apiClient.get<AutomationStats>('/zero-touch/stats');
  return response.data;
}

/**
 * Genehmigt eine Rechnung
 *
 * @param id - ID des Freigabe-Items
 */
export async function approveInvoice(id: string): Promise<ApproveRejectResponse> {
  const response = await apiClient.post<ApproveRejectResponse>(
    `/zero-touch/approve/${id}`
  );
  return response.data;
}

/**
 * Lehnt eine Rechnung ab
 *
 * @param id - ID des Freigabe-Items
 */
export async function rejectInvoice(id: string): Promise<ApproveRejectResponse> {
  const response = await apiClient.post<ApproveRejectResponse>(
    `/zero-touch/reject/${id}`
  );
  return response.data;
}
