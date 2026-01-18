/**
 * Predictive Actions API Service
 *
 * Kommuniziert mit den /api/v1/predictive-actions Endpoints
 * fuer proaktive Handlungsvorschlaege
 *
 * Features:
 * - Aktionsvorschlaege abrufen (kritisch, skonto, mahnung)
 * - Aktionen akzeptieren/ablehnen/verschieben
 * - Statistiken und Feedback
 *
 * Phase 2.2 der Feature-Roadmap (Januar 2026)
 */

import { AxiosError } from 'axios';
import { apiClient } from '../client';

// ==================== Error Classes ====================

export class PredictiveActionsApiError extends Error {
  statusCode?: number;
  originalError?: unknown;

  constructor(message: string, statusCode?: number, originalError?: unknown) {
    super(message);
    this.name = 'PredictiveActionsApiError';
    this.statusCode = statusCode;
    this.originalError = originalError;
  }
}

// ==================== Enums ====================

export type ActionType =
  | 'send_dunning'
  | 'call_customer'
  | 'use_skonto'
  | 'pay_invoice'
  | 'renew_contract'
  | 'cancel_contract'
  | 'adjust_budget'
  | 'review_budget'
  | 'schedule_payment'
  | 'check_payment'
  | 'custom';

export type TriggerType =
  | 'dunning_due'
  | 'skonto_expiring'
  | 'contract_ending'
  | 'budget_warning'
  | 'payment_due'
  | 'manual';

export type ActionPriority = 'critical' | 'high' | 'medium' | 'low';
export type ActionStatus = 'pending' | 'shown' | 'accepted' | 'rejected' | 'snoozed' | 'executed' | 'expired';

// ==================== Frontend Types ====================

export interface PredictiveAction {
  id: string;
  actionType: ActionType;
  triggerType: TriggerType;
  priority: ActionPriority;

  title: string;
  description: string;
  benefitText: string;

  targetId: string;
  targetType: string;

  confidence: number;
  deadline?: string;
  suggestedActionTime?: string;

  status: ActionStatus;
  createdAt: string;

  metadata: ActionMetadata;
}

export interface ActionMetadata {
  invoiceNumber?: string;
  amount?: number;
  daysOverdue?: number;
  daysRemaining?: number;
  skontoPercentage?: number;
  skontoAmount?: number;
  skontoDeadline?: string;
  contractName?: string;
  budgetName?: string;
  utilizationPercent?: number;
  [key: string]: unknown;
}

export interface PredictiveActionsListResponse {
  actions: PredictiveAction[];
  total: number;
  summary: ActionsSummary;
}

export interface ActionsSummary {
  critical?: number;
  high?: number;
  medium?: number;
  low?: number;
  totalPotentialSavings?: number;
  expiringToday?: number;
  expiringThisWeek?: number;
  totalOutstanding?: number;
  criticalCount?: number;
  needsCall?: number;
  [key: string]: number | undefined;
}

export interface ActionResult {
  success: boolean;
  message: string;
  actionId: string;
  newStatus: ActionStatus;
  snoozeUntil?: string;
}

export interface ActionStatistics {
  periodStart: string;
  periodEnd: string;

  totalSuggested: number;
  totalAccepted: number;
  totalRejected: number;
  totalSnoozed: number;

  acceptanceRate: number;
  effectivenessRate: number;

  estimatedSavings: number;
  realizedSavings: number;

  byActionType: Record<string, number>;
  byPriority: Record<string, number>;
}

export interface ActionTypesResponse {
  actionTypes: ActionType[];
  triggerTypes: TriggerType[];
  priorities: ActionPriority[];
  statuses: ActionStatus[];
}

// ==================== Request Types ====================

export interface AcceptActionRequest {
  executeImmediately?: boolean;
}

export interface RejectActionRequest {
  reason?: string;
}

export interface SnoozeActionRequest {
  snoozeHours?: number;
}

export interface PredictiveActionsFilter {
  limit?: number;
  actionTypes?: ActionType[];
  minPriority?: ActionPriority;
}

// ==================== Backend Types ====================

interface PredictiveActionBackend {
  id: string;
  action_type: string;
  trigger_type: string;
  priority: string;

  title: string;
  description: string;
  benefit_text: string;

  target_id: string;
  target_type: string;

  confidence: number;
  deadline: string | null;
  suggested_action_time: string | null;

  status: string;
  created_at: string;

  metadata: Record<string, unknown>;
}

interface PredictiveActionsListBackend {
  actions: PredictiveActionBackend[];
  total: number;
  summary: Record<string, number>;
}

interface ActionResultBackend {
  success: boolean;
  message: string;
  action_id: string;
  new_status: string;
  snooze_until: string | null;
}

interface ActionStatisticsBackend {
  period_start: string;
  period_end: string;

  total_suggested: number;
  total_accepted: number;
  total_rejected: number;
  total_snoozed: number;

  acceptance_rate: number;
  effectiveness_rate: number;

  estimated_savings: number;
  realized_savings: number;

  by_action_type: Record<string, number>;
  by_priority: Record<string, number>;
}

interface ActionTypesBackend {
  action_types: string[];
  trigger_types: string[];
  priorities: string[];
  statuses: string[];
}

// ==================== Transformers ====================

function transformAction(a: PredictiveActionBackend): PredictiveAction {
  return {
    id: a.id,
    actionType: a.action_type as ActionType,
    triggerType: a.trigger_type as TriggerType,
    priority: a.priority as ActionPriority,
    title: a.title,
    description: a.description,
    benefitText: a.benefit_text,
    targetId: a.target_id,
    targetType: a.target_type,
    confidence: a.confidence,
    deadline: a.deadline ?? undefined,
    suggestedActionTime: a.suggested_action_time ?? undefined,
    status: a.status as ActionStatus,
    createdAt: a.created_at,
    metadata: transformMetadata(a.metadata),
  };
}

function transformMetadata(m: Record<string, unknown>): ActionMetadata {
  return {
    invoiceNumber: m.invoice_number as string | undefined,
    amount: m.amount as number | undefined,
    daysOverdue: m.days_overdue as number | undefined,
    daysRemaining: m.days_remaining as number | undefined,
    skontoPercentage: m.skonto_percentage as number | undefined,
    skontoAmount: m.skonto_amount as number | undefined,
    skontoDeadline: m.skonto_deadline as string | undefined,
    contractName: m.contract_name as string | undefined,
    budgetName: m.budget_name as string | undefined,
    utilizationPercent: m.utilization_percent as number | undefined,
    ...m,
  };
}

function transformSummary(s: Record<string, number>): ActionsSummary {
  return {
    critical: s.critical,
    high: s.high,
    medium: s.medium,
    low: s.low,
    totalPotentialSavings: s.total_potential_savings,
    expiringToday: s.expiring_today,
    expiringThisWeek: s.expiring_this_week,
    totalOutstanding: s.total_outstanding,
    criticalCount: s.critical_count,
    needsCall: s.needs_call,
  };
}

function transformActionResult(r: ActionResultBackend): ActionResult {
  return {
    success: r.success,
    message: r.message,
    actionId: r.action_id,
    newStatus: r.new_status as ActionStatus,
    snoozeUntil: r.snooze_until ?? undefined,
  };
}

function transformStatistics(s: ActionStatisticsBackend): ActionStatistics {
  return {
    periodStart: s.period_start,
    periodEnd: s.period_end,
    totalSuggested: s.total_suggested,
    totalAccepted: s.total_accepted,
    totalRejected: s.total_rejected,
    totalSnoozed: s.total_snoozed,
    acceptanceRate: s.acceptance_rate,
    effectivenessRate: s.effectiveness_rate,
    estimatedSavings: s.estimated_savings,
    realizedSavings: s.realized_savings,
    byActionType: s.by_action_type,
    byPriority: s.by_priority,
  };
}

// ==================== Error Handler ====================

function handleApiError(error: unknown, context: string): never {
  if (error instanceof AxiosError) {
    const statusCode = error.response?.status;
    const message = error.response?.data?.detail || error.message;

    if (statusCode === 404) {
      throw new PredictiveActionsApiError(`${context}: Nicht gefunden`, 404, error);
    }

    if (statusCode === 400) {
      throw new PredictiveActionsApiError(`${context}: ${message}`, 400, error);
    }

    throw new PredictiveActionsApiError(`${context}: ${message}`, statusCode, error);
  }

  throw new PredictiveActionsApiError(`${context}: Unbekannter Fehler`, undefined, error);
}

// ==================== Service ====================

export const predictiveActionsService = {
  /**
   * Holt alle Aktionsvorschlaege
   */
  getActions: async (filter?: PredictiveActionsFilter): Promise<PredictiveActionsListResponse> => {
    try {
      const params = new URLSearchParams();
      if (filter?.limit) params.append('limit', String(filter.limit));
      if (filter?.actionTypes?.length) params.append('action_types', filter.actionTypes.join(','));
      if (filter?.minPriority) params.append('min_priority', filter.minPriority);

      const url = `/predictive-actions${params.toString() ? `?${params.toString()}` : ''}`;
      const response = await apiClient.get<PredictiveActionsListBackend>(url);

      return {
        actions: response.data.actions.map(transformAction),
        total: response.data.total,
        summary: transformSummary(response.data.summary),
      };
    } catch (error) {
      if (error instanceof AxiosError && error.response?.status === 404) {
        return { actions: [], total: 0, summary: {} };
      }
      handleApiError(error, 'Aktionen laden');
    }
  },

  /**
   * Holt kritische Aktionen fuer Dashboard
   */
  getCriticalActions: async (limit = 10): Promise<PredictiveActionsListResponse> => {
    try {
      const response = await apiClient.get<PredictiveActionsListBackend>(
        `/predictive-actions/critical?limit=${limit}`
      );

      return {
        actions: response.data.actions.map(transformAction),
        total: response.data.total,
        summary: transformSummary(response.data.summary),
      };
    } catch (error) {
      if (error instanceof AxiosError && error.response?.status === 404) {
        return { actions: [], total: 0, summary: {} };
      }
      handleApiError(error, 'Kritische Aktionen laden');
    }
  },

  /**
   * Holt Skonto-spezifische Vorschlaege
   */
  getSkontoActions: async (limit = 20): Promise<PredictiveActionsListResponse> => {
    try {
      const response = await apiClient.get<PredictiveActionsListBackend>(
        `/predictive-actions/skonto?limit=${limit}`
      );

      return {
        actions: response.data.actions.map(transformAction),
        total: response.data.total,
        summary: transformSummary(response.data.summary),
      };
    } catch (error) {
      if (error instanceof AxiosError && error.response?.status === 404) {
        return { actions: [], total: 0, summary: {} };
      }
      handleApiError(error, 'Skonto-Aktionen laden');
    }
  },

  /**
   * Holt Mahnungs-spezifische Vorschlaege
   */
  getDunningActions: async (limit = 20): Promise<PredictiveActionsListResponse> => {
    try {
      const response = await apiClient.get<PredictiveActionsListBackend>(
        `/predictive-actions/dunning?limit=${limit}`
      );

      return {
        actions: response.data.actions.map(transformAction),
        total: response.data.total,
        summary: transformSummary(response.data.summary),
      };
    } catch (error) {
      if (error instanceof AxiosError && error.response?.status === 404) {
        return { actions: [], total: 0, summary: {} };
      }
      handleApiError(error, 'Mahnungs-Aktionen laden');
    }
  },

  /**
   * Akzeptiert eine Aktion
   */
  acceptAction: async (
    actionId: string,
    request: AcceptActionRequest = {}
  ): Promise<ActionResult> => {
    try {
      const response = await apiClient.post<ActionResultBackend>(
        `/predictive-actions/${actionId}/accept`,
        {
          execute_immediately: request.executeImmediately ?? false,
        }
      );
      return transformActionResult(response.data);
    } catch (error) {
      handleApiError(error, 'Aktion akzeptieren');
    }
  },

  /**
   * Lehnt eine Aktion ab
   */
  rejectAction: async (
    actionId: string,
    request: RejectActionRequest = {}
  ): Promise<ActionResult> => {
    try {
      const response = await apiClient.post<ActionResultBackend>(
        `/predictive-actions/${actionId}/reject`,
        {
          reason: request.reason,
        }
      );
      return transformActionResult(response.data);
    } catch (error) {
      handleApiError(error, 'Aktion ablehnen');
    }
  },

  /**
   * Verschiebt eine Aktion
   */
  snoozeAction: async (
    actionId: string,
    request: SnoozeActionRequest = {}
  ): Promise<ActionResult> => {
    try {
      const response = await apiClient.post<ActionResultBackend>(
        `/predictive-actions/${actionId}/snooze`,
        {
          snooze_hours: request.snoozeHours ?? 24,
        }
      );
      return transformActionResult(response.data);
    } catch (error) {
      handleApiError(error, 'Aktion verschieben');
    }
  },

  /**
   * Holt Statistiken zu Aktionsvorschlaegen
   */
  getStatistics: async (days = 30): Promise<ActionStatistics> => {
    try {
      const response = await apiClient.get<ActionStatisticsBackend>(
        `/predictive-actions/statistics?days=${days}`
      );
      return transformStatistics(response.data);
    } catch (error) {
      handleApiError(error, 'Statistiken laden');
    }
  },

  /**
   * Holt verfuegbare Typen
   */
  getActionTypes: async (): Promise<ActionTypesResponse> => {
    try {
      const response = await apiClient.get<ActionTypesBackend>('/predictive-actions/types');
      return {
        actionTypes: response.data.action_types as ActionType[],
        triggerTypes: response.data.trigger_types as TriggerType[],
        priorities: response.data.priorities as ActionPriority[],
        statuses: response.data.statuses as ActionStatus[],
      };
    } catch (error) {
      handleApiError(error, 'Typen laden');
    }
  },
};
