/**
 * Company API Service
 *
 * API-Client für Multi-Mandanten Firmenverwaltung.
 */

import { apiClient } from '../client';
import type {
  Company,
  CompanyCreate,
  CompanyUpdate,
  CompanyListResponse,
  UserCompany,
  UserCompanyCreate,
  UserCompanyUpdate,
} from '@/types/models/company';

// ==================== Company Service ====================

export const companyService = {
  /**
   * Firmen des aktuellen Benutzers auflisten
   */
  async list(params?: {
    skip?: number;
    limit?: number;
    include_inactive?: boolean;
  }): Promise<CompanyListResponse> {
    const response = await apiClient.get<CompanyListResponse>('/companies', { params });
    return response.data;
  },

  /**
   * Aktuelle Firma abrufen
   */
  async getCurrent(): Promise<Company | null> {
    const response = await apiClient.get<Company | null>('/companies/current');
    return response.data;
  },

  /**
   * Firma wechseln
   */
  async switchCompany(companyId: string): Promise<Company> {
    const response = await apiClient.post<Company>(`/companies/current/${companyId}`);
    return response.data;
  },

  /**
   * Firma abrufen
   */
  async get(companyId: string): Promise<Company> {
    const response = await apiClient.get<Company>(`/companies/${companyId}`);
    return response.data;
  },

  /**
   * Firma erstellen
   */
  async create(data: CompanyCreate): Promise<Company> {
    const response = await apiClient.post<Company>('/companies', data);
    return response.data;
  },

  /**
   * Firma aktualisieren
   */
  async update(companyId: string, data: CompanyUpdate): Promise<Company> {
    const response = await apiClient.put<Company>(`/companies/${companyId}`, data);
    return response.data;
  },

  /**
   * Firma löschen (Soft-Delete)
   */
  async delete(companyId: string): Promise<void> {
    await apiClient.delete(`/companies/${companyId}`);
  },

  // ==================== User Management ====================

  /**
   * Benutzer einer Firma auflisten
   */
  async listUsers(companyId: string): Promise<UserCompany[]> {
    const response = await apiClient.get<UserCompany[]>(`/companies/${companyId}/users`);
    return response.data;
  },

  /**
   * Benutzer zu Firma hinzufügen
   */
  async addUser(companyId: string, data: UserCompanyCreate): Promise<UserCompany> {
    const response = await apiClient.post<UserCompany>(`/companies/${companyId}/users`, data);
    return response.data;
  },

  /**
   * Benutzerrolle aktualisieren
   */
  async updateUser(companyId: string, userId: string, data: UserCompanyUpdate): Promise<UserCompany> {
    const response = await apiClient.put<UserCompany>(`/companies/${companyId}/users/${userId}`, data);
    return response.data;
  },

  /**
   * Benutzer aus Firma entfernen
   */
  async removeUser(companyId: string, userId: string): Promise<void> {
    await apiClient.delete(`/companies/${companyId}/users/${userId}`);
  },

  // ==================== Dashboard ====================

  /**
   * Multi-Firma Dashboard abrufen
   */
  async getDashboard(params?: {
    include_inactive?: boolean;
  }): Promise<CompanyDashboardResponse> {
    const response = await apiClient.get<CompanyDashboardResponse>('/companies/dashboard', { params });
    return response.data;
  },

  /**
   * Firmen-Vergleich abrufen
   */
  async getComparison(params: {
    metric: string;
    company_ids?: string;
  }): Promise<CompanyComparisonResponse> {
    const response = await apiClient.get<CompanyComparisonResponse>('/companies/comparison', { params });
    return response.data;
  },

  /**
   * Metriken einer Firma abrufen
   */
  async getMetrics(companyId: string): Promise<CompanyMetrics> {
    const response = await apiClient.get<CompanyMetrics>(`/companies/${companyId}/metrics`);
    return response.data;
  },
};

// ==================== Dashboard Types ====================

export interface CompanyMetrics {
  company_id: string;
  company_name: string;
  company_short_name: string | null;
  is_active: boolean;
  health_score: number;
  documents: {
    total: number;
    this_month: number;
    last_month: number;
    growth_percent: number;
  };
  invoices: {
    total: number;
    total_amount: number;
    paid_amount: number;
    outstanding_amount: number;
    overdue_count: number;
    overdue_amount: number;
    average_payment_days: number;
  };
  entities: {
    total: number;
    customers: number;
    suppliers: number;
    high_risk: number;
  };
  dunning: {
    active: number;
    total_amount: number;
    by_level: {
      '1': number;
      '2': number;
      '3': number;
      '4': number;
    };
  };
  banking: {
    balance: number;
    incoming_this_month: number;
    outgoing_this_month: number;
    unmatched_transactions: number;
  };
}

export interface DashboardSummary {
  total_companies: number;
  active_companies: number;
  total_documents: number;
  total_invoices: number;
  total_outstanding_amount: number;
  total_overdue_amount: number;
  total_entities: number;
  active_dunnings: number;
}

export interface DashboardAlert {
  type: 'critical' | 'warning';
  company_id: string;
  company_name: string;
  message: string;
  action: string;
}

export interface CompanyDashboardResponse {
  summary: DashboardSummary;
  companies: CompanyMetrics[];
  alerts: DashboardAlert[];
}

export interface CompanyComparisonData {
  company_id: string;
  company_name: string;
  company_short_name: string | null;
  metric_type: string;
  value: number;
  details: Record<string, unknown>;
}

export interface CompanyComparisonResponse {
  metric: string;
  metric_label: string;
  data: CompanyComparisonData[];
}

export default companyService;
