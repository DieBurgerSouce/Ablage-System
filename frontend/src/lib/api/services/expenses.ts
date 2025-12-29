/**
 * Expense API Service
 *
 * API-Client für Spesenabrechnung mit Workflow.
 */

import { apiClient } from '../client';
import type {
  ExpenseReport,
  ExpenseReportCreate,
  ExpenseReportUpdate,
  ExpenseReportListResponse,
  ExpenseItem,
  ExpenseItemCreate,
  ExpenseItemUpdate,
  ExpenseReportApproveRequest,
  ExpenseReportRejectRequest,
  ExpenseReportPayRequest,
  PerDiemCalculateRequest,
  PerDiemCalculation,
  MileageCalculateRequest,
  MileageCalculation,
  ExpenseReportStatus,
} from '@/types/models/expense';

// ==================== Expense Service ====================

export const expenseService = {
  // ==================== Reports ====================

  /**
   * Spesenabrechnungen auflisten
   */
  async listReports(params?: {
    employee_id?: string;
    status?: ExpenseReportStatus;
    start_date?: string;
    end_date?: string;
    skip?: number;
    limit?: number;
  }): Promise<ExpenseReportListResponse> {
    const response = await apiClient.get<ExpenseReportListResponse>('/expenses/reports', { params });
    return response.data;
  },

  /**
   * Spesenabrechnung abrufen
   */
  async getReport(reportId: string): Promise<ExpenseReport> {
    const response = await apiClient.get<ExpenseReport>(`/expenses/reports/${reportId}`);
    return response.data;
  },

  /**
   * Spesenabrechnung erstellen
   */
  async createReport(data: ExpenseReportCreate): Promise<ExpenseReport> {
    const response = await apiClient.post<ExpenseReport>('/expenses/reports', data);
    return response.data;
  },

  /**
   * Spesenabrechnung aktualisieren
   */
  async updateReport(reportId: string, data: ExpenseReportUpdate): Promise<ExpenseReport> {
    const response = await apiClient.put<ExpenseReport>(`/expenses/reports/${reportId}`, data);
    return response.data;
  },

  /**
   * Spesenabrechnung löschen
   */
  async deleteReport(reportId: string): Promise<void> {
    await apiClient.delete(`/expenses/reports/${reportId}`);
  },

  // ==================== Items ====================

  /**
   * Position hinzufügen
   */
  async addItem(reportId: string, data: ExpenseItemCreate): Promise<ExpenseItem> {
    const response = await apiClient.post<ExpenseItem>(`/expenses/reports/${reportId}/items`, data);
    return response.data;
  },

  /**
   * Position aktualisieren
   */
  async updateItem(itemId: string, data: ExpenseItemUpdate): Promise<ExpenseItem> {
    const response = await apiClient.put<ExpenseItem>(`/expenses/items/${itemId}`, data);
    return response.data;
  },

  /**
   * Position löschen
   */
  async deleteItem(itemId: string): Promise<void> {
    await apiClient.delete(`/expenses/items/${itemId}`);
  },

  // ==================== Workflow ====================

  /**
   * Spesenabrechnung einreichen
   */
  async submitReport(reportId: string): Promise<ExpenseReport> {
    const response = await apiClient.post<ExpenseReport>(`/expenses/reports/${reportId}/submit`);
    return response.data;
  },

  /**
   * Spesenabrechnung genehmigen
   */
  async approveReport(reportId: string, data: ExpenseReportApproveRequest): Promise<ExpenseReport> {
    const response = await apiClient.post<ExpenseReport>(`/expenses/reports/${reportId}/approve`, data);
    return response.data;
  },

  /**
   * Spesenabrechnung ablehnen
   */
  async rejectReport(reportId: string, data: ExpenseReportRejectRequest): Promise<ExpenseReport> {
    const response = await apiClient.post<ExpenseReport>(`/expenses/reports/${reportId}/reject`, data);
    return response.data;
  },

  /**
   * Spesenabrechnung auszahlen
   */
  async payReport(reportId: string, data: ExpenseReportPayRequest): Promise<ExpenseReport> {
    const response = await apiClient.post<ExpenseReport>(`/expenses/reports/${reportId}/pay`, data);
    return response.data;
  },

  // ==================== Calculators ====================

  /**
   * Verpflegungspauschale berechnen
   */
  async calculatePerDiem(data: PerDiemCalculateRequest): Promise<PerDiemCalculation> {
    const response = await apiClient.post<PerDiemCalculation>('/expenses/calculate/per-diem', data);
    return response.data;
  },

  /**
   * Kilometergeld berechnen
   */
  async calculateMileage(data: MileageCalculateRequest): Promise<MileageCalculation> {
    const response = await apiClient.post<MileageCalculation>('/expenses/calculate/mileage', data);
    return response.data;
  },
};

export default expenseService;
