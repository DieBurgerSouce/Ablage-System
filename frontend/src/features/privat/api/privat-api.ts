/**
 * Privat-Modul API Client
 *
 * API-Aufrufe für das persoenliche Dokumentenmanagement:
 * - Spaces, Ordner, Dokumente
 * - Immobilien, Fahrzeuge, Versicherungen
 * - Kredite, Geldanlagen
 * - Fristen, Notfallzugriff
 */

import type {
  PrivatSpaceCreate,
  PrivatSpaceUpdate,
  PrivatSpaceWithStats,
  PrivatSpaceAccessCreate,
  PrivatSpaceAccess,
  PrivatFolderCreate,
  PrivatFolderUpdate,
  PrivatFolder,
  PrivatFolderTree,
  PrivatDocumentCreate,
  PrivatDocumentUpdate,
  PrivatDocument,
  PrivatDocumentListResponse,
  PrivatDocumentType,
  PrivatPropertyCreate,
  PrivatPropertyUpdate,
  PrivatPropertyWithDetails,
  PrivatPropertyListResponse,
  PrivatTenantCreate,
  PrivatTenantUpdate,
  PrivatTenant,
  PrivatRentalIncomeCreate,
  PrivatRentalIncome,
  PrivatVehicleCreate,
  PrivatVehicleUpdate,
  PrivatVehicleWithStats,
  PrivatVehicleListResponse,
  VehicleType,
  PrivatFuelLogCreate,
  PrivatFuelLog,
  PrivatFuelStatistics,
  PrivatInsuranceCreate,
  PrivatInsuranceUpdate,
  PrivatInsuranceWithDeadlines,
  PrivatInsuranceListResponse,
  InsuranceType,
  PrivatLoanCreate,
  PrivatLoanUpdate,
  PrivatLoanWithStats,
  PrivatLoanListResponse,
  LoanType,
  PrivatInvestmentCreate,
  PrivatInvestmentUpdate,
  PrivatInvestmentWithStats,
  PrivatInvestmentListResponse,
  InvestmentType,
  PrivatPortfolioBreakdown,
  PrivatDeadlineCreate,
  PrivatDeadlineUpdate,
  PrivatDeadlineWithStatus,
  PrivatDeadlineListResponse,
  PrivatDeadlineWidget,
  PrivatDeadlineType,
  PrivatEmergencyContactCreate,
  PrivatEmergencyContactUpdate,
  PrivatEmergencyContact,
  PrivatEmergencyAccessRequestCreate,
  PrivatEmergencyAccessRequest,
  PrivatEmergencyAccessStatus,
  PrivatDashboardStats,
  PrivatFinancialSummary,
} from '@/types/privat';

const API_BASE = '/api/v1/privat';

// ==================== Helper Functions ====================

function buildQueryString(params: Record<string, unknown>): string {
  const searchParams = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      // Convert camelCase to snake_case
      const snakeKey = key.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`);
      searchParams.append(snakeKey, String(value));
    }
  });
  const queryString = searchParams.toString();
  return queryString ? `?${queryString}` : '';
}

async function apiRequest<T>(url: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    credentials: 'include',
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `API Fehler: ${response.status}`);
  }

  // Handle empty responses (204 No Content)
  if (response.status === 204) {
    return undefined as T;
  }

  return response.json();
}

// ==================== Dashboard API ====================

export async function getDashboardStats(): Promise<PrivatDashboardStats> {
  return apiRequest<PrivatDashboardStats>(`${API_BASE}/dashboard`);
}

export async function getFinancialSummary(spaceId: string): Promise<PrivatFinancialSummary> {
  return apiRequest<PrivatFinancialSummary>(`${API_BASE}/dashboard/financial-summary?space_id=${spaceId}`);
}

// ==================== Space API ====================

export async function listSpaces(): Promise<PrivatSpaceWithStats[]> {
  return apiRequest<PrivatSpaceWithStats[]>(`${API_BASE}/spaces`);
}

export async function getSpace(spaceId: string): Promise<PrivatSpaceWithStats> {
  return apiRequest<PrivatSpaceWithStats>(`${API_BASE}/spaces/${spaceId}`);
}

export async function createSpace(data: PrivatSpaceCreate): Promise<PrivatSpaceWithStats> {
  return apiRequest<PrivatSpaceWithStats>(`${API_BASE}/spaces`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateSpace(spaceId: string, data: PrivatSpaceUpdate): Promise<PrivatSpaceWithStats> {
  return apiRequest<PrivatSpaceWithStats>(`${API_BASE}/spaces/${spaceId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

export async function deleteSpace(spaceId: string): Promise<void> {
  return apiRequest<void>(`${API_BASE}/spaces/${spaceId}`, {
    method: 'DELETE',
  });
}

// ==================== Space Access API ====================

export async function grantAccess(spaceId: string, data: PrivatSpaceAccessCreate): Promise<PrivatSpaceAccess> {
  return apiRequest<PrivatSpaceAccess>(`${API_BASE}/spaces/${spaceId}/access`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function listAccess(spaceId: string): Promise<PrivatSpaceAccess[]> {
  return apiRequest<PrivatSpaceAccess[]>(`${API_BASE}/spaces/${spaceId}/access`);
}

export async function revokeAccess(spaceId: string, userId: string): Promise<void> {
  return apiRequest<void>(`${API_BASE}/spaces/${spaceId}/access/${userId}`, {
    method: 'DELETE',
  });
}

// ==================== Folder API ====================

export async function getFolderTree(spaceId: string): Promise<PrivatFolderTree[]> {
  return apiRequest<PrivatFolderTree[]>(`${API_BASE}/spaces/${spaceId}/folders`);
}

export async function createFolder(spaceId: string, data: PrivatFolderCreate): Promise<PrivatFolder> {
  return apiRequest<PrivatFolder>(`${API_BASE}/spaces/${spaceId}/folders`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateFolder(folderId: string, data: PrivatFolderUpdate): Promise<PrivatFolder> {
  return apiRequest<PrivatFolder>(`${API_BASE}/folders/${folderId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

export async function moveFolder(folderId: string, newParentId?: string): Promise<PrivatFolder> {
  const query = newParentId ? `?new_parent_id=${newParentId}` : '';
  return apiRequest<PrivatFolder>(`${API_BASE}/folders/${folderId}/move${query}`, {
    method: 'POST',
  });
}

export async function deleteFolder(folderId: string, recursive = false): Promise<void> {
  return apiRequest<void>(`${API_BASE}/folders/${folderId}?recursive=${recursive}`, {
    method: 'DELETE',
  });
}

// ==================== Document API ====================

export interface DocumentFilters {
  folderId?: string;
  documentType?: PrivatDocumentType;
  search?: string;
  page?: number;
  pageSize?: number;
}

export async function listDocuments(spaceId: string, filters: DocumentFilters = {}): Promise<PrivatDocumentListResponse> {
  const queryString = buildQueryString(filters);
  return apiRequest<PrivatDocumentListResponse>(`${API_BASE}/spaces/${spaceId}/documents${queryString}`);
}

export async function getDocument(documentId: string): Promise<PrivatDocument> {
  return apiRequest<PrivatDocument>(`${API_BASE}/documents/${documentId}`);
}

export async function createDocument(spaceId: string, data: PrivatDocumentCreate, password?: string): Promise<PrivatDocument> {
  // Security: Passwort wird per Header statt URL-Parameter gesendet
  // (vermeidet Logging in Browser History/Server Logs)
  const headers: Record<string, string> = {};
  if (password) {
    headers['X-Privat-Password'] = password;
  }
  return apiRequest<PrivatDocument>(`${API_BASE}/spaces/${spaceId}/documents`, {
    method: 'POST',
    body: JSON.stringify(data),
    headers,
  });
}

export async function updateDocument(documentId: string, data: PrivatDocumentUpdate): Promise<PrivatDocument> {
  return apiRequest<PrivatDocument>(`${API_BASE}/documents/${documentId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

export async function deleteDocument(documentId: string): Promise<void> {
  return apiRequest<void>(`${API_BASE}/documents/${documentId}`, {
    method: 'DELETE',
  });
}

/**
 * Gibt die Download-URL ohne Passwort zurück.
 * WARNUNG: Fuer passwortgeschützte Dokumente sollte downloadDocument() verwendet werden!
 */
export function getDocumentDownloadUrl(documentId: string): string {
  return `${API_BASE}/documents/${documentId}/content`;
}

/**
 * Lädt ein Dokument herunter (unterstützt passwortgeschützte Dokumente).
 * Security: Passwort wird per Header gesendet, nicht per URL.
 */
export async function downloadDocument(documentId: string, password?: string): Promise<Blob> {
  const headers: Record<string, string> = {};
  if (password) {
    headers['X-Privat-Password'] = password;
  }

  const token = sessionStorage.getItem('auth_token');
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}/documents/${documentId}/content`, {
    method: 'GET',
    headers,
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Download fehlgeschlagen' }));
    throw new Error(errorData.detail || `HTTP ${response.status}`);
  }

  return response.blob();
}

/**
 * Lädt ein Dokument herunter und speichert es.
 * Ersetzt direkte Link-Downloads für passwortgeschützte Dokumente.
 */
export async function downloadAndSaveDocument(
  documentId: string,
  filename: string,
  password?: string
): Promise<void> {
  const blob = await downloadDocument(documentId, password);

  // Create download link and trigger download
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

// ==================== Property API ====================

export interface PropertyFilters {
  search?: string;
  page?: number;
  pageSize?: number;
}

export async function listProperties(spaceId: string, filters: PropertyFilters = {}): Promise<PrivatPropertyListResponse> {
  const queryString = buildQueryString(filters);
  return apiRequest<PrivatPropertyListResponse>(`${API_BASE}/spaces/${spaceId}/properties${queryString}`);
}

export async function getProperty(propertyId: string): Promise<PrivatPropertyWithDetails> {
  return apiRequest<PrivatPropertyWithDetails>(`${API_BASE}/properties/${propertyId}`);
}

export async function createProperty(spaceId: string, data: PrivatPropertyCreate): Promise<PrivatPropertyWithDetails> {
  return apiRequest<PrivatPropertyWithDetails>(`${API_BASE}/spaces/${spaceId}/properties`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateProperty(propertyId: string, data: PrivatPropertyUpdate): Promise<PrivatPropertyWithDetails> {
  return apiRequest<PrivatPropertyWithDetails>(`${API_BASE}/properties/${propertyId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

export async function deleteProperty(propertyId: string): Promise<void> {
  return apiRequest<void>(`${API_BASE}/properties/${propertyId}`, {
    method: 'DELETE',
  });
}

// ==================== Tenant API ====================

export async function listTenants(propertyId: string, activeOnly = true): Promise<PrivatTenant[]> {
  return apiRequest<PrivatTenant[]>(`${API_BASE}/properties/${propertyId}/tenants?active_only=${activeOnly}`);
}

export async function createTenant(propertyId: string, data: PrivatTenantCreate): Promise<PrivatTenant> {
  return apiRequest<PrivatTenant>(`${API_BASE}/properties/${propertyId}/tenants`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function recordRentalIncome(tenantId: string, data: PrivatRentalIncomeCreate): Promise<PrivatRentalIncome> {
  return apiRequest<PrivatRentalIncome>(`${API_BASE}/tenants/${tenantId}/income`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// ==================== Vehicle API ====================

export interface VehicleFilters {
  vehicleType?: VehicleType;
  search?: string;
  page?: number;
  pageSize?: number;
}

export async function listVehicles(spaceId: string, filters: VehicleFilters = {}): Promise<PrivatVehicleListResponse> {
  const queryString = buildQueryString(filters);
  return apiRequest<PrivatVehicleListResponse>(`${API_BASE}/spaces/${spaceId}/vehicles${queryString}`);
}

export async function getVehicle(vehicleId: string): Promise<PrivatVehicleWithStats> {
  return apiRequest<PrivatVehicleWithStats>(`${API_BASE}/vehicles/${vehicleId}`);
}

export async function createVehicle(spaceId: string, data: PrivatVehicleCreate): Promise<PrivatVehicleWithStats> {
  return apiRequest<PrivatVehicleWithStats>(`${API_BASE}/spaces/${spaceId}/vehicles`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateVehicle(vehicleId: string, data: PrivatVehicleUpdate): Promise<PrivatVehicleWithStats> {
  return apiRequest<PrivatVehicleWithStats>(`${API_BASE}/vehicles/${vehicleId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

export async function deleteVehicle(vehicleId: string): Promise<void> {
  return apiRequest<void>(`${API_BASE}/vehicles/${vehicleId}`, {
    method: 'DELETE',
  });
}

// ==================== Fuel Log API ====================

export interface FuelLogFilters {
  startDate?: string;
  endDate?: string;
}

export async function listFuelLogs(vehicleId: string, filters: FuelLogFilters = {}): Promise<PrivatFuelLog[]> {
  const queryString = buildQueryString(filters);
  return apiRequest<PrivatFuelLog[]>(`${API_BASE}/vehicles/${vehicleId}/fuel${queryString}`);
}

export async function createFuelLog(vehicleId: string, data: PrivatFuelLogCreate): Promise<PrivatFuelLog> {
  return apiRequest<PrivatFuelLog>(`${API_BASE}/vehicles/${vehicleId}/fuel`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function getFuelStatistics(vehicleId: string): Promise<PrivatFuelStatistics> {
  return apiRequest<PrivatFuelStatistics>(`${API_BASE}/vehicles/${vehicleId}/fuel/statistics`);
}

// ==================== Insurance API ====================

export interface InsuranceFilters {
  insuranceType?: InsuranceType;
  page?: number;
  pageSize?: number;
}

export async function listInsurances(spaceId: string, filters: InsuranceFilters = {}): Promise<PrivatInsuranceListResponse> {
  const queryString = buildQueryString(filters);
  return apiRequest<PrivatInsuranceListResponse>(`${API_BASE}/spaces/${spaceId}/insurances${queryString}`);
}

export async function createInsurance(spaceId: string, data: PrivatInsuranceCreate): Promise<PrivatInsuranceWithDeadlines> {
  return apiRequest<PrivatInsuranceWithDeadlines>(`${API_BASE}/spaces/${spaceId}/insurances`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateInsurance(insuranceId: string, data: PrivatInsuranceUpdate): Promise<PrivatInsuranceWithDeadlines> {
  return apiRequest<PrivatInsuranceWithDeadlines>(`${API_BASE}/insurances/${insuranceId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

export async function deleteInsurance(insuranceId: string): Promise<void> {
  return apiRequest<void>(`${API_BASE}/insurances/${insuranceId}`, {
    method: 'DELETE',
  });
}

// ==================== Loan API ====================

export interface LoanFilters {
  loanType?: LoanType;
  page?: number;
  pageSize?: number;
}

export async function listLoans(spaceId: string, filters: LoanFilters = {}): Promise<PrivatLoanListResponse> {
  const queryString = buildQueryString(filters);
  return apiRequest<PrivatLoanListResponse>(`${API_BASE}/spaces/${spaceId}/loans${queryString}`);
}

export async function createLoan(spaceId: string, data: PrivatLoanCreate): Promise<PrivatLoanWithStats> {
  return apiRequest<PrivatLoanWithStats>(`${API_BASE}/spaces/${spaceId}/loans`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateLoan(loanId: string, data: PrivatLoanUpdate): Promise<PrivatLoanWithStats> {
  return apiRequest<PrivatLoanWithStats>(`${API_BASE}/loans/${loanId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

export async function recordLoanPayment(loanId: string, amount: number, paymentDate?: string): Promise<PrivatLoanWithStats> {
  const params = { amount, payment_date: paymentDate };
  const queryString = buildQueryString(params);
  return apiRequest<PrivatLoanWithStats>(`${API_BASE}/loans/${loanId}/payment${queryString}`, {
    method: 'POST',
  });
}

export async function deleteLoan(loanId: string): Promise<void> {
  return apiRequest<void>(`${API_BASE}/loans/${loanId}`, {
    method: 'DELETE',
  });
}

// ==================== Investment API ====================

export interface InvestmentFilters {
  investmentType?: InvestmentType;
  page?: number;
  pageSize?: number;
}

export async function listInvestments(spaceId: string, filters: InvestmentFilters = {}): Promise<PrivatInvestmentListResponse> {
  const queryString = buildQueryString(filters);
  return apiRequest<PrivatInvestmentListResponse>(`${API_BASE}/spaces/${spaceId}/investments${queryString}`);
}

export async function createInvestment(spaceId: string, data: PrivatInvestmentCreate): Promise<PrivatInvestmentWithStats> {
  return apiRequest<PrivatInvestmentWithStats>(`${API_BASE}/spaces/${spaceId}/investments`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateInvestment(investmentId: string, data: PrivatInvestmentUpdate): Promise<PrivatInvestmentWithStats> {
  return apiRequest<PrivatInvestmentWithStats>(`${API_BASE}/investments/${investmentId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

export async function updateInvestmentValue(investmentId: string, newValue: number): Promise<PrivatInvestmentWithStats> {
  return apiRequest<PrivatInvestmentWithStats>(`${API_BASE}/investments/${investmentId}/value?new_value=${newValue}`, {
    method: 'POST',
  });
}

export async function deleteInvestment(investmentId: string): Promise<void> {
  return apiRequest<void>(`${API_BASE}/investments/${investmentId}`, {
    method: 'DELETE',
  });
}

export async function getPortfolioBreakdown(spaceId: string): Promise<PrivatPortfolioBreakdown> {
  return apiRequest<PrivatPortfolioBreakdown>(`${API_BASE}/spaces/${spaceId}/investments/portfolio`);
}

// ==================== Deadline API ====================

export interface DeadlineFilters {
  includeCompleted?: boolean;
  deadlineType?: PrivatDeadlineType;
  page?: number;
  pageSize?: number;
}

export async function listDeadlines(spaceId: string, filters: DeadlineFilters = {}): Promise<PrivatDeadlineListResponse> {
  const queryString = buildQueryString(filters);
  return apiRequest<PrivatDeadlineListResponse>(`${API_BASE}/spaces/${spaceId}/deadlines${queryString}`);
}

export async function getDeadlineWidget(spaceId: string): Promise<PrivatDeadlineWidget> {
  return apiRequest<PrivatDeadlineWidget>(`${API_BASE}/spaces/${spaceId}/deadlines/widget`);
}

export async function createDeadline(spaceId: string, data: PrivatDeadlineCreate): Promise<PrivatDeadlineWithStatus> {
  return apiRequest<PrivatDeadlineWithStatus>(`${API_BASE}/spaces/${spaceId}/deadlines`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateDeadline(deadlineId: string, data: PrivatDeadlineUpdate): Promise<PrivatDeadlineWithStatus> {
  return apiRequest<PrivatDeadlineWithStatus>(`${API_BASE}/deadlines/${deadlineId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

export async function completeDeadline(deadlineId: string): Promise<PrivatDeadlineWithStatus> {
  return apiRequest<PrivatDeadlineWithStatus>(`${API_BASE}/deadlines/${deadlineId}/complete`, {
    method: 'POST',
  });
}

export async function deleteDeadline(deadlineId: string): Promise<void> {
  return apiRequest<void>(`${API_BASE}/deadlines/${deadlineId}`, {
    method: 'DELETE',
  });
}

export function getCalendarExportUrl(spaceId: string, includeCompleted = false): string {
  return `${API_BASE}/spaces/${spaceId}/deadlines/calendar?include_completed=${includeCompleted}`;
}

// ==================== Emergency Access API ====================

export async function listEmergencyContacts(spaceId: string): Promise<PrivatEmergencyContact[]> {
  return apiRequest<PrivatEmergencyContact[]>(`${API_BASE}/spaces/${spaceId}/emergency/contacts`);
}

export async function createEmergencyContact(spaceId: string, data: PrivatEmergencyContactCreate): Promise<PrivatEmergencyContact> {
  return apiRequest<PrivatEmergencyContact>(`${API_BASE}/spaces/${spaceId}/emergency/contacts`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateEmergencyContact(contactId: string, data: PrivatEmergencyContactUpdate): Promise<PrivatEmergencyContact> {
  return apiRequest<PrivatEmergencyContact>(`${API_BASE}/emergency/contacts/${contactId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

export async function deleteEmergencyContact(contactId: string): Promise<void> {
  return apiRequest<void>(`${API_BASE}/emergency/contacts/${contactId}`, {
    method: 'DELETE',
  });
}

export async function requestEmergencyAccess(data: PrivatEmergencyAccessRequestCreate): Promise<PrivatEmergencyAccessRequest> {
  return apiRequest<PrivatEmergencyAccessRequest>(`${API_BASE}/emergency/request`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function listEmergencyRequests(spaceId: string, status?: PrivatEmergencyAccessStatus): Promise<PrivatEmergencyAccessRequest[]> {
  const query = status ? `?status_filter=${status}` : '';
  return apiRequest<PrivatEmergencyAccessRequest[]>(`${API_BASE}/spaces/${spaceId}/emergency/requests${query}`);
}

export async function approveEmergencyRequest(requestId: string): Promise<PrivatEmergencyAccessRequest> {
  return apiRequest<PrivatEmergencyAccessRequest>(`${API_BASE}/emergency/requests/${requestId}/approve`, {
    method: 'POST',
  });
}

export async function denyEmergencyRequest(requestId: string, reason: string): Promise<PrivatEmergencyAccessRequest> {
  return apiRequest<PrivatEmergencyAccessRequest>(`${API_BASE}/emergency/requests/${requestId}/deny?reason=${encodeURIComponent(reason)}`, {
    method: 'POST',
  });
}

export async function revokeEmergencyAccess(requestId: string): Promise<void> {
  return apiRequest<void>(`${API_BASE}/emergency/requests/${requestId}/revoke`, {
    method: 'POST',
  });
}
