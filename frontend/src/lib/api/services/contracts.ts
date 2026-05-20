/**
 * Contract Service API
 *
 * API client for contract management endpoints.
 * Mirrors contract_service_v2.py backend service.
 */

import { apiClient } from '../client';
import type {
  Contract,
  ContractDetail,
  ContractListResponse,
  ContractListParams,
  ContractCreateRequest,
  ContractUpdateRequest,
  ContractSummary,
  DeadlineListResponse,
  ContractTimeline,
  ContractMilestone,
  MilestoneCreateRequest,
  MilestoneUpdateRequest,
  ContractRenewalOption,
  RenewalOptionDecision,
  ContractAmendment,
  AmendmentCreateRequest,
  AmendmentUpdateRequest,
} from '@/features/contracts/types/contract-types';

const API_BASE = '/contracts';

// =============================================================================
// Types for iCal Export
// =============================================================================

export interface ICalExportParams {
  days_ahead?: number;
  contract_ids?: string[];
}

export interface ICalExportResponse {
  ical_content: string;
  filename: string;
  event_count: number;
}

// =============================================================================
// Contract Service
// =============================================================================

export const contractsService = {
  // ==================== Contract CRUD ====================

  /**
   * Liste aller Verträge mit optionalen Filtern
   */
  listContracts: async (params: ContractListParams = {}): Promise<ContractListResponse> => {
    const response = await apiClient.get<ContractListResponse>(API_BASE, { params });
    return response.data;
  },

  /**
   * Einzelnen Vertrag abrufen
   */
  getContract: async (id: string): Promise<ContractDetail> => {
    const response = await apiClient.get<ContractDetail>(`${API_BASE}/${id}`);
    return response.data;
  },

  /**
   * Neuen Vertrag erstellen
   */
  createContract: async (data: ContractCreateRequest): Promise<Contract> => {
    const response = await apiClient.post<Contract>(API_BASE, data);
    return response.data;
  },

  /**
   * Vertrag aktualisieren
   */
  updateContract: async (id: string, data: ContractUpdateRequest): Promise<Contract> => {
    const response = await apiClient.patch<Contract>(`${API_BASE}/${id}`, data);
    return response.data;
  },

  /**
   * Vertrag löschen
   */
  deleteContract: async (id: string): Promise<void> => {
    await apiClient.delete(`${API_BASE}/${id}`);
  },

  // ==================== Summary & Deadlines ====================

  /**
   * Vertragsstatistiken abrufen
   */
  getSummary: async (): Promise<ContractSummary> => {
    const response = await apiClient.get<ContractSummary>(`${API_BASE}/summary`);
    return response.data;
  },

  /**
   * Anstehende Fristen abrufen
   */
  getUpcomingDeadlines: async (daysAhead: number = 90): Promise<DeadlineListResponse> => {
    const response = await apiClient.get<DeadlineListResponse>(`${API_BASE}/deadlines`, {
      params: { days_ahead: daysAhead },
    });
    return response.data;
  },

  /**
   * Timeline eines Vertrags abrufen
   */
  getContractTimeline: async (id: string): Promise<ContractTimeline> => {
    const response = await apiClient.get<ContractTimeline>(`${API_BASE}/${id}/timeline`);
    return response.data;
  },

  // ==================== iCal Export ====================

  /**
   * Fristen als iCal exportieren
   */
  exportToICal: async (params: ICalExportParams = {}): Promise<ICalExportResponse> => {
    const response = await apiClient.get<ICalExportResponse>(`${API_BASE}/export/ical`, {
      params,
    });
    return response.data;
  },

  /**
   * iCal-Datei herunterladen
   */
  downloadICal: async (params: ICalExportParams = {}): Promise<Blob> => {
    const response = await apiClient.get(`${API_BASE}/export/ical/download`, {
      params,
      responseType: 'blob',
    });
    return response.data;
  },

  // ==================== Milestones ====================

  /**
   * Meilenstein erstellen
   */
  createMilestone: async (contractId: string, data: MilestoneCreateRequest): Promise<ContractMilestone> => {
    const response = await apiClient.post<ContractMilestone>(`${API_BASE}/${contractId}/milestones`, data);
    return response.data;
  },

  /**
   * Meilenstein aktualisieren
   */
  updateMilestone: async (
    contractId: string,
    milestoneId: string,
    data: MilestoneUpdateRequest
  ): Promise<ContractMilestone> => {
    const response = await apiClient.patch<ContractMilestone>(
      `${API_BASE}/${contractId}/milestones/${milestoneId}`,
      data
    );
    return response.data;
  },

  /**
   * Meilenstein löschen
   */
  deleteMilestone: async (contractId: string, milestoneId: string): Promise<void> => {
    await apiClient.delete(`${API_BASE}/${contractId}/milestones/${milestoneId}`);
  },

  /**
   * Meilenstein als erledigt markieren
   */
  completeMilestone: async (
    contractId: string,
    milestoneId: string,
    notes?: string
  ): Promise<ContractMilestone> => {
    const response = await apiClient.post<ContractMilestone>(
      `${API_BASE}/${contractId}/milestones/${milestoneId}/complete`,
      { notes }
    );
    return response.data;
  },

  // ==================== Renewal Options ====================

  /**
   * Verlängerungsoptionen abrufen
   */
  listRenewalOptions: async (contractId: string): Promise<ContractRenewalOption[]> => {
    const response = await apiClient.get<ContractRenewalOption[]>(`${API_BASE}/${contractId}/renewal-options`);
    return response.data;
  },

  /**
   * Verlängerungsentscheidung treffen
   */
  makeRenewalDecision: async (
    contractId: string,
    optionId: string,
    data: RenewalOptionDecision
  ): Promise<ContractRenewalOption> => {
    const response = await apiClient.post<ContractRenewalOption>(
      `${API_BASE}/${contractId}/renewal-options/${optionId}/decision`,
      data
    );
    return response.data;
  },

  // ==================== Amendments ====================

  /**
   * Nachtrag erstellen
   */
  createAmendment: async (contractId: string, data: AmendmentCreateRequest): Promise<ContractAmendment> => {
    const response = await apiClient.post<ContractAmendment>(`${API_BASE}/${contractId}/amendments`, data);
    return response.data;
  },

  /**
   * Nachtrag aktualisieren
   */
  updateAmendment: async (
    contractId: string,
    amendmentId: string,
    data: AmendmentUpdateRequest
  ): Promise<ContractAmendment> => {
    const response = await apiClient.patch<ContractAmendment>(
      `${API_BASE}/${contractId}/amendments/${amendmentId}`,
      data
    );
    return response.data;
  },

  /**
   * Nachtrag löschen
   */
  deleteAmendment: async (contractId: string, amendmentId: string): Promise<void> => {
    await apiClient.delete(`${API_BASE}/${contractId}/amendments/${amendmentId}`);
  },

  /**
   * Nachtrag genehmigen
   */
  approveAmendment: async (contractId: string, amendmentId: string): Promise<ContractAmendment> => {
    const response = await apiClient.post<ContractAmendment>(
      `${API_BASE}/${contractId}/amendments/${amendmentId}/approve`
    );
    return response.data;
  },

  // ==================== Bulk Operations ====================

  /**
   * Mehrere Verträge exportieren
   */
  bulkExport: async (contractIds: string[], format: 'csv' | 'xlsx' | 'pdf' = 'xlsx'): Promise<Blob> => {
    const response = await apiClient.post(
      `${API_BASE}/bulk/export`,
      { contract_ids: contractIds, format },
      { responseType: 'blob' }
    );
    return response.data;
  },

  /**
   * Erinnerungen für mehrere Verträge senden
   */
  bulkSendReminders: async (contractIds: string[]): Promise<{ sent: number; failed: number }> => {
    const response = await apiClient.post<{ sent: number; failed: number }>(
      `${API_BASE}/bulk/send-reminders`,
      { contract_ids: contractIds }
    );
    return response.data;
  },
};

export default contractsService;
