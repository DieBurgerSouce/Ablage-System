/**
 * Rules API Service
 *
 * Standalone service layer for Business Rules CRUD operations.
 * Used by TanStack Query hooks in features/admin/rules.
 */

import { apiClient } from '../client';
import type {
  BusinessRule,
  RuleListResponse,
  RuleCreateRequest,
  RuleUpdateRequest,
  RuleTestRequest,
  RuleTestResponse,
  OperatorsResponse,
  ExecutionLog,
} from '@/features/admin/rules/types';

export interface RuleListParams {
  page?: number;
  per_page?: number;
  category?: string;
  is_active?: boolean;
  search?: string;
  limit?: number;
  offset?: number;
}

export interface ExecutionLogParams {
  rule_id?: string;
  document_id?: string;
  matched_only?: boolean;
  limit?: number;
  offset?: number;
}

export const rulesService = {
  /**
   * Regeln auflisten (paginiert)
   */
  fetchRules: async (params?: RuleListParams): Promise<RuleListResponse> => {
    const response = await apiClient.get<RuleListResponse>('/rules', { params });
    return response.data;
  },

  /**
   * Einzelne Regel abrufen
   */
  fetchRule: async (id: string): Promise<BusinessRule> => {
    const response = await apiClient.get<BusinessRule>(`/rules/${id}`);
    return response.data;
  },

  /**
   * Neue Regel erstellen
   */
  createRule: async (data: RuleCreateRequest): Promise<BusinessRule> => {
    const response = await apiClient.post<BusinessRule>('/rules', data);
    return response.data;
  },

  /**
   * Regel aktualisieren
   */
  updateRule: async (id: string, data: RuleUpdateRequest): Promise<BusinessRule> => {
    const response = await apiClient.patch<BusinessRule>(`/rules/${id}`, data);
    return response.data;
  },

  /**
   * Regel loeschen
   */
  deleteRule: async (id: string): Promise<void> => {
    await apiClient.delete(`/rules/${id}`);
  },

  /**
   * Regel testen (Dry-Run)
   */
  testRule: async (data: RuleTestRequest): Promise<RuleTestResponse> => {
    const response = await apiClient.post<RuleTestResponse>('/rules/test', data);
    return response.data;
  },

  /**
   * Regel aktiv/inaktiv umschalten
   */
  toggleRule: async (id: string): Promise<BusinessRule> => {
    const response = await apiClient.post<BusinessRule>(`/rules/${id}/toggle`);
    return response.data;
  },

  /**
   * Dokument gegen Regeln evaluieren
   */
  evaluateRules: async (documentContext: Record<string, unknown>): Promise<RuleTestResponse[]> => {
    const response = await apiClient.post<RuleTestResponse[]>('/rules/evaluate', documentContext);
    return response.data;
  },

  /**
   * Verfuegbare Operatoren abrufen
   */
  fetchOperators: async (): Promise<OperatorsResponse> => {
    const response = await apiClient.get<OperatorsResponse>('/rules/schema/operators');
    return response.data;
  },

  /**
   * Ausfuehrungslogs abrufen
   */
  fetchExecutionLogs: async (params?: ExecutionLogParams): Promise<ExecutionLog[]> => {
    const response = await apiClient.get<ExecutionLog[]>('/rules/logs', { params });
    return response.data;
  },

  /**
   * Regel aus natuerlicher Sprache generieren
   */
  generateRule: async (prompt: string): Promise<Record<string, unknown>> => {
    const response = await apiClient.post<Record<string, unknown>>('/rules/generate', { prompt });
    return response.data;
  },
};
