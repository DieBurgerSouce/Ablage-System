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
};

export default companyService;
