/**
 * Privat-Modul API Client
 *
 * API-Aufrufe für das persönliche Dokumentenmanagement:
 * - Spaces, Ordner, Dokumente
 * - Immobilien, Fahrzeuge, Versicherungen
 * - Kredite, Geldanlagen
 * - Fristen, Notfallzugriff
 *
 * Migriert zu apiClient für:
 * - Automatische Retry-Logik
 * - Error-Toast-Handler
 * - Token-Refresh-Behandlung
 * - Konsistente Fehlerbehandlung
 */

import { apiClient } from '@/lib/api/client';
import type { PrivatSpaceCreate, PrivatSpaceUpdate, PrivatSpaceWithStats, PrivatSpaceAccessCreate, PrivatSpaceAccess, PrivatFolderCreate, PrivatFolderUpdate, PrivatFolder, PrivatFolderTree, PrivatDocumentCreate, PrivatDocumentUpdate, PrivatDocument, PrivatDocumentListResponse, PrivatDocumentType, PrivatPropertyCreate, PrivatPropertyUpdate, PrivatPropertyWithDetails, PrivatPropertyListResponse, PrivatTenantCreate, PrivatTenant, PrivatRentalIncomeCreate, PrivatRentalIncome, PrivatVehicleCreate, PrivatVehicleUpdate, PrivatVehicleWithStats, PrivatVehicleListResponse, VehicleType, PrivatFuelLogCreate, PrivatFuelLog, PrivatFuelStatistics, PrivatInsuranceCreate, PrivatInsuranceUpdate, PrivatInsuranceWithDeadlines, PrivatInsuranceListResponse, InsuranceType, PrivatLoanCreate, PrivatLoanUpdate, PrivatLoanWithStats, PrivatLoanListResponse, LoanType, PrivatInvestmentCreate, PrivatInvestmentUpdate, PrivatInvestmentWithStats, PrivatInvestmentListResponse, InvestmentType, PrivatPortfolioBreakdown, PrivatDeadlineCreate, PrivatDeadlineUpdate, PrivatDeadlineWithStatus, PrivatDeadlineListResponse, PrivatDeadlineWidget, PrivatDeadlineType, PrivatEmergencyContactCreate, PrivatEmergencyContactUpdate, PrivatEmergencyContact, PrivatEmergencyAccessRequestCreate, PrivatEmergencyAccessRequest, PrivatEmergencyAccessStatus, PrivatDashboardStats, PrivatFinancialSummary } from '@/types/privat';

// Base URL without /api/v1/ prefix (apiClient already has it)
const BASE_URL = '/privat';

// ==================== Helper Functions ====================

/**
 * Transformiert ein Objekt von snake_case zu camelCase (rekursiv).
 * Wird für API-Responses verwendet.
 */
function toCamelCase<T>(obj: T): T {
  if (obj === null || obj === undefined) return obj;
  if (typeof obj !== 'object') return obj;
  if (Array.isArray(obj)) {
    return obj.map(toCamelCase) as T;
  }
  if (obj instanceof Date) return obj as T;

  return Object.fromEntries(
    Object.entries(obj as Record<string, unknown>).map(([key, value]) => [
      key.replace(/_([a-z])/g, (_, letter: string) => letter.toUpperCase()),
      toCamelCase(value),
    ])
  ) as T;
}

/**
 * Transformiert ein Objekt von camelCase zu snake_case (rekursiv).
 * Wird für API-Request-Bodies verwendet.
 */
function toSnakeCase<T>(obj: T): T {
  if (obj === null || obj === undefined) return obj;
  if (typeof obj !== 'object') return obj;
  if (Array.isArray(obj)) {
    return obj.map(toSnakeCase) as T;
  }
  if (obj instanceof Date) return obj as T;

  return Object.fromEntries(
    Object.entries(obj as Record<string, unknown>).map(([key, value]) => [
      key.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`),
      toSnakeCase(value),
    ])
  ) as T;
}

function buildQueryParams(params: Record<string, unknown>): Record<string, string> {
  const result: Record<string, string> = {};
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      // Convert camelCase to snake_case
      const snakeKey = key.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`);
      result[snakeKey] = String(value);
    }
  });
  return result;
}

// ==================== Dashboard API ====================

export async function getDashboardStats(): Promise<PrivatDashboardStats> {
  const response = await apiClient.get<PrivatDashboardStats>(`${BASE_URL}/dashboard`);
  return toCamelCase(response.data);
}

export async function getFinancialSummary(spaceId: string): Promise<PrivatFinancialSummary> {
  const response = await apiClient.get<PrivatFinancialSummary>(`${BASE_URL}/dashboard/financial-summary`, {
    params: { space_id: spaceId },
  });
  return toCamelCase(response.data);
}

// ==================== Space API ====================

export async function listSpaces(): Promise<PrivatSpaceWithStats[]> {
  const response = await apiClient.get<PrivatSpaceWithStats[]>(`${BASE_URL}/spaces`);
  return toCamelCase(response.data);
}

export async function getSpace(spaceId: string): Promise<PrivatSpaceWithStats> {
  const response = await apiClient.get<PrivatSpaceWithStats>(`${BASE_URL}/spaces/${spaceId}`);
  return toCamelCase(response.data);
}

export async function createSpace(data: PrivatSpaceCreate): Promise<PrivatSpaceWithStats> {
  const response = await apiClient.post<PrivatSpaceWithStats>(`${BASE_URL}/spaces`, toSnakeCase(data));
  return toCamelCase(response.data);
}

export async function updateSpace(spaceId: string, data: PrivatSpaceUpdate): Promise<PrivatSpaceWithStats> {
  const response = await apiClient.patch<PrivatSpaceWithStats>(`${BASE_URL}/spaces/${spaceId}`, toSnakeCase(data));
  return toCamelCase(response.data);
}

export async function deleteSpace(spaceId: string): Promise<void> {
  await apiClient.delete(`${BASE_URL}/spaces/${spaceId}`);
}

// ==================== Space Access API ====================

export async function grantAccess(spaceId: string, data: PrivatSpaceAccessCreate): Promise<PrivatSpaceAccess> {
  const response = await apiClient.post<PrivatSpaceAccess>(`${BASE_URL}/spaces/${spaceId}/access`, toSnakeCase(data));
  return toCamelCase(response.data);
}

export async function listAccess(spaceId: string): Promise<PrivatSpaceAccess[]> {
  const response = await apiClient.get<PrivatSpaceAccess[]>(`${BASE_URL}/spaces/${spaceId}/access`);
  return toCamelCase(response.data);
}

export async function revokeAccess(spaceId: string, userId: string): Promise<void> {
  await apiClient.delete(`${BASE_URL}/spaces/${spaceId}/access/${userId}`);
}

// ==================== Folder API ====================

export async function getFolderTree(spaceId: string): Promise<PrivatFolderTree[]> {
  const response = await apiClient.get<PrivatFolderTree[]>(`${BASE_URL}/spaces/${spaceId}/folders`);
  return toCamelCase(response.data);
}

export async function createFolder(spaceId: string, data: PrivatFolderCreate): Promise<PrivatFolder> {
  const response = await apiClient.post<PrivatFolder>(`${BASE_URL}/spaces/${spaceId}/folders`, toSnakeCase(data));
  return toCamelCase(response.data);
}

export async function updateFolder(folderId: string, data: PrivatFolderUpdate): Promise<PrivatFolder> {
  const response = await apiClient.patch<PrivatFolder>(`${BASE_URL}/folders/${folderId}`, toSnakeCase(data));
  return toCamelCase(response.data);
}

export async function moveFolder(folderId: string, newParentId?: string): Promise<PrivatFolder> {
  const response = await apiClient.post<PrivatFolder>(`${BASE_URL}/folders/${folderId}/move`, null, {
    params: newParentId ? { new_parent_id: newParentId } : undefined,
  });
  return toCamelCase(response.data);
}

export async function deleteFolder(folderId: string, recursive = false): Promise<void> {
  await apiClient.delete(`${BASE_URL}/folders/${folderId}`, {
    params: { recursive },
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
  const response = await apiClient.get<PrivatDocumentListResponse>(`${BASE_URL}/spaces/${spaceId}/documents`, {
    params: buildQueryParams(filters),
  });
  return toCamelCase(response.data);
}

export async function getDocument(documentId: string): Promise<PrivatDocument> {
  const response = await apiClient.get<PrivatDocument>(`${BASE_URL}/documents/${documentId}`);
  return toCamelCase(response.data);
}

export async function createDocument(spaceId: string, data: PrivatDocumentCreate, password?: string): Promise<PrivatDocument> {
  // Security: Passwort wird per Header statt URL-Parameter gesendet
  // (vermeidet Logging in Browser History/Server Logs)
  const headers: Record<string, string> = {};
  if (password) {
    headers['X-Privat-Password'] = password;
  }
  const response = await apiClient.post<PrivatDocument>(`${BASE_URL}/spaces/${spaceId}/documents`, toSnakeCase(data), { headers });
  return toCamelCase(response.data);
}

export async function updateDocument(documentId: string, data: PrivatDocumentUpdate): Promise<PrivatDocument> {
  const response = await apiClient.patch<PrivatDocument>(`${BASE_URL}/documents/${documentId}`, toSnakeCase(data));
  return toCamelCase(response.data);
}

export async function deleteDocument(documentId: string): Promise<void> {
  await apiClient.delete(`${BASE_URL}/documents/${documentId}`);
}

/**
 * Gibt die Download-URL ohne Passwort zurück.
 * WARNUNG: Für passwortgeschützte Dokumente sollte downloadDocument() verwendet werden!
 */
export function getDocumentDownloadUrl(documentId: string): string {
  // Muss volle URL inkl. /api/v1 sein für direkte Browser-Downloads
  return `/api/v1${BASE_URL}/documents/${documentId}/content`;
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

  const response = await apiClient.get(`${BASE_URL}/documents/${documentId}/content`, {
    headers,
    responseType: 'blob',
  });

  return response.data;
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
  const response = await apiClient.get<PrivatPropertyListResponse>(`${BASE_URL}/spaces/${spaceId}/properties`, {
    params: buildQueryParams(filters),
  });
  return toCamelCase(response.data);
}

export async function getProperty(propertyId: string): Promise<PrivatPropertyWithDetails> {
  const response = await apiClient.get<PrivatPropertyWithDetails>(`${BASE_URL}/properties/${propertyId}`);
  return toCamelCase(response.data);
}

export async function createProperty(spaceId: string, data: PrivatPropertyCreate): Promise<PrivatPropertyWithDetails> {
  const response = await apiClient.post<PrivatPropertyWithDetails>(`${BASE_URL}/spaces/${spaceId}/properties`, toSnakeCase(data));
  return toCamelCase(response.data);
}

export async function updateProperty(propertyId: string, data: PrivatPropertyUpdate): Promise<PrivatPropertyWithDetails> {
  const response = await apiClient.patch<PrivatPropertyWithDetails>(`${BASE_URL}/properties/${propertyId}`, toSnakeCase(data));
  return toCamelCase(response.data);
}

export async function deleteProperty(propertyId: string): Promise<void> {
  await apiClient.delete(`${BASE_URL}/properties/${propertyId}`);
}

// ==================== Tenant API ====================

export async function listTenants(propertyId: string, activeOnly = true): Promise<PrivatTenant[]> {
  const response = await apiClient.get<PrivatTenant[]>(`${BASE_URL}/properties/${propertyId}/tenants`, {
    params: buildQueryParams({ activeOnly }),
  });
  return toCamelCase(response.data);
}

export async function createTenant(propertyId: string, data: PrivatTenantCreate): Promise<PrivatTenant> {
  const response = await apiClient.post<PrivatTenant>(`${BASE_URL}/properties/${propertyId}/tenants`, toSnakeCase(data));
  return toCamelCase(response.data);
}

export async function recordRentalIncome(tenantId: string, data: PrivatRentalIncomeCreate): Promise<PrivatRentalIncome> {
  const response = await apiClient.post<PrivatRentalIncome>(`${BASE_URL}/tenants/${tenantId}/income`, toSnakeCase(data));
  return toCamelCase(response.data);
}

// ==================== Vehicle API ====================

export interface VehicleFilters {
  vehicleType?: VehicleType;
  search?: string;
  page?: number;
  pageSize?: number;
}

export async function listVehicles(spaceId: string, filters: VehicleFilters = {}): Promise<PrivatVehicleListResponse> {
  const response = await apiClient.get<PrivatVehicleListResponse>(`${BASE_URL}/spaces/${spaceId}/vehicles`, {
    params: buildQueryParams(filters),
  });
  return toCamelCase(response.data);
}

export async function getVehicle(vehicleId: string): Promise<PrivatVehicleWithStats> {
  const response = await apiClient.get<PrivatVehicleWithStats>(`${BASE_URL}/vehicles/${vehicleId}`);
  return toCamelCase(response.data);
}

export async function createVehicle(spaceId: string, data: PrivatVehicleCreate): Promise<PrivatVehicleWithStats> {
  const response = await apiClient.post<PrivatVehicleWithStats>(`${BASE_URL}/spaces/${spaceId}/vehicles`, toSnakeCase(data));
  return toCamelCase(response.data);
}

export async function updateVehicle(vehicleId: string, data: PrivatVehicleUpdate): Promise<PrivatVehicleWithStats> {
  const response = await apiClient.patch<PrivatVehicleWithStats>(`${BASE_URL}/vehicles/${vehicleId}`, toSnakeCase(data));
  return toCamelCase(response.data);
}

export async function deleteVehicle(vehicleId: string): Promise<void> {
  await apiClient.delete(`${BASE_URL}/vehicles/${vehicleId}`);
}

// ==================== Fuel Log API ====================

export interface FuelLogFilters {
  startDate?: string;
  endDate?: string;
}

export async function listFuelLogs(vehicleId: string, filters: FuelLogFilters = {}): Promise<PrivatFuelLog[]> {
  const response = await apiClient.get<PrivatFuelLog[]>(`${BASE_URL}/vehicles/${vehicleId}/fuel`, {
    params: buildQueryParams(filters),
  });
  return toCamelCase(response.data);
}

export async function createFuelLog(vehicleId: string, data: PrivatFuelLogCreate): Promise<PrivatFuelLog> {
  const response = await apiClient.post<PrivatFuelLog>(`${BASE_URL}/vehicles/${vehicleId}/fuel`, toSnakeCase(data));
  return toCamelCase(response.data);
}

export async function getFuelStatistics(vehicleId: string): Promise<PrivatFuelStatistics> {
  const response = await apiClient.get<PrivatFuelStatistics>(`${BASE_URL}/vehicles/${vehicleId}/fuel/statistics`);
  return toCamelCase(response.data);
}

// ==================== Insurance API ====================

export interface InsuranceFilters {
  insuranceType?: InsuranceType;
  page?: number;
  pageSize?: number;
}

export async function listInsurances(spaceId: string, filters: InsuranceFilters = {}): Promise<PrivatInsuranceListResponse> {
  const response = await apiClient.get<PrivatInsuranceListResponse>(`${BASE_URL}/spaces/${spaceId}/insurances`, {
    params: buildQueryParams(filters),
  });
  return toCamelCase(response.data);
}

export async function getInsurance(insuranceId: string): Promise<PrivatInsuranceWithDeadlines> {
  const response = await apiClient.get<PrivatInsuranceWithDeadlines>(`${BASE_URL}/insurances/${insuranceId}`);
  return toCamelCase(response.data);
}

export async function createInsurance(spaceId: string, data: PrivatInsuranceCreate): Promise<PrivatInsuranceWithDeadlines> {
  const response = await apiClient.post<PrivatInsuranceWithDeadlines>(`${BASE_URL}/spaces/${spaceId}/insurances`, toSnakeCase(data));
  return toCamelCase(response.data);
}

export async function updateInsurance(insuranceId: string, data: PrivatInsuranceUpdate): Promise<PrivatInsuranceWithDeadlines> {
  const response = await apiClient.patch<PrivatInsuranceWithDeadlines>(`${BASE_URL}/insurances/${insuranceId}`, toSnakeCase(data));
  return toCamelCase(response.data);
}

export async function deleteInsurance(insuranceId: string): Promise<void> {
  await apiClient.delete(`${BASE_URL}/insurances/${insuranceId}`);
}

// ==================== Loan API ====================

export interface LoanFilters {
  loanType?: LoanType;
  page?: number;
  pageSize?: number;
}

export async function listLoans(spaceId: string, filters: LoanFilters = {}): Promise<PrivatLoanListResponse> {
  const response = await apiClient.get<PrivatLoanListResponse>(`${BASE_URL}/spaces/${spaceId}/loans`, {
    params: buildQueryParams(filters),
  });
  return toCamelCase(response.data);
}

export async function getLoan(loanId: string): Promise<PrivatLoanWithStats> {
  const response = await apiClient.get<PrivatLoanWithStats>(`${BASE_URL}/loans/${loanId}`);
  return toCamelCase(response.data);
}

export async function createLoan(spaceId: string, data: PrivatLoanCreate): Promise<PrivatLoanWithStats> {
  const response = await apiClient.post<PrivatLoanWithStats>(`${BASE_URL}/spaces/${spaceId}/loans`, toSnakeCase(data));
  return toCamelCase(response.data);
}

export async function updateLoan(loanId: string, data: PrivatLoanUpdate): Promise<PrivatLoanWithStats> {
  const response = await apiClient.patch<PrivatLoanWithStats>(`${BASE_URL}/loans/${loanId}`, toSnakeCase(data));
  return toCamelCase(response.data);
}

export async function recordLoanPayment(loanId: string, amount: number, paymentDate?: string): Promise<PrivatLoanWithStats> {
  const response = await apiClient.post<PrivatLoanWithStats>(`${BASE_URL}/loans/${loanId}/payment`, null, {
    params: buildQueryParams({ amount, paymentDate }),
  });
  return toCamelCase(response.data);
}

export async function deleteLoan(loanId: string): Promise<void> {
  await apiClient.delete(`${BASE_URL}/loans/${loanId}`);
}

// ==================== Investment API ====================

export interface InvestmentFilters {
  investmentType?: InvestmentType;
  page?: number;
  pageSize?: number;
}

export async function listInvestments(spaceId: string, filters: InvestmentFilters = {}): Promise<PrivatInvestmentListResponse> {
  const response = await apiClient.get<PrivatInvestmentListResponse>(`${BASE_URL}/spaces/${spaceId}/investments`, {
    params: buildQueryParams(filters),
  });
  return toCamelCase(response.data);
}

export async function getInvestment(investmentId: string): Promise<PrivatInvestmentWithStats> {
  const response = await apiClient.get<PrivatInvestmentWithStats>(`${BASE_URL}/investments/${investmentId}`);
  return toCamelCase(response.data);
}

export async function createInvestment(spaceId: string, data: PrivatInvestmentCreate): Promise<PrivatInvestmentWithStats> {
  const response = await apiClient.post<PrivatInvestmentWithStats>(`${BASE_URL}/spaces/${spaceId}/investments`, toSnakeCase(data));
  return toCamelCase(response.data);
}

export async function updateInvestment(investmentId: string, data: PrivatInvestmentUpdate): Promise<PrivatInvestmentWithStats> {
  const response = await apiClient.patch<PrivatInvestmentWithStats>(`${BASE_URL}/investments/${investmentId}`, toSnakeCase(data));
  return toCamelCase(response.data);
}

export async function updateInvestmentValue(investmentId: string, newValue: number): Promise<PrivatInvestmentWithStats> {
  const response = await apiClient.post<PrivatInvestmentWithStats>(`${BASE_URL}/investments/${investmentId}/value`, null, {
    params: buildQueryParams({ newValue }),
  });
  return toCamelCase(response.data);
}

export async function deleteInvestment(investmentId: string): Promise<void> {
  await apiClient.delete(`${BASE_URL}/investments/${investmentId}`);
}

export async function getPortfolioBreakdown(spaceId: string): Promise<PrivatPortfolioBreakdown> {
  const response = await apiClient.get<PrivatPortfolioBreakdown>(`${BASE_URL}/spaces/${spaceId}/investments/portfolio`);
  return toCamelCase(response.data);
}

// ==================== Deadline API ====================

export interface DeadlineFilters {
  includeCompleted?: boolean;
  deadlineType?: PrivatDeadlineType;
  page?: number;
  pageSize?: number;
}

export async function listDeadlines(spaceId: string, filters: DeadlineFilters = {}): Promise<PrivatDeadlineListResponse> {
  const response = await apiClient.get<PrivatDeadlineListResponse>(`${BASE_URL}/spaces/${spaceId}/deadlines`, {
    params: buildQueryParams(filters),
  });
  return toCamelCase(response.data);
}

export async function getDeadlineWidget(spaceId: string): Promise<PrivatDeadlineWidget> {
  const response = await apiClient.get<PrivatDeadlineWidget>(`${BASE_URL}/spaces/${spaceId}/deadlines/widget`);
  return toCamelCase(response.data);
}

export async function createDeadline(spaceId: string, data: PrivatDeadlineCreate): Promise<PrivatDeadlineWithStatus> {
  const response = await apiClient.post<PrivatDeadlineWithStatus>(`${BASE_URL}/spaces/${spaceId}/deadlines`, toSnakeCase(data));
  return toCamelCase(response.data);
}

export async function updateDeadline(deadlineId: string, data: PrivatDeadlineUpdate): Promise<PrivatDeadlineWithStatus> {
  const response = await apiClient.patch<PrivatDeadlineWithStatus>(`${BASE_URL}/deadlines/${deadlineId}`, toSnakeCase(data));
  return toCamelCase(response.data);
}

export async function completeDeadline(deadlineId: string): Promise<PrivatDeadlineWithStatus> {
  const response = await apiClient.post<PrivatDeadlineWithStatus>(`${BASE_URL}/deadlines/${deadlineId}/complete`);
  return toCamelCase(response.data);
}

export async function deleteDeadline(deadlineId: string): Promise<void> {
  await apiClient.delete(`${BASE_URL}/deadlines/${deadlineId}`);
}

export function getCalendarExportUrl(spaceId: string, includeCompleted = false): string {
  // Muss volle URL inkl. /api/v1 sein für direkte Browser-Downloads
  return `/api/v1${BASE_URL}/spaces/${spaceId}/deadlines/calendar?include_completed=${includeCompleted}`;
}

// ==================== Emergency Access API ====================

export async function listEmergencyContacts(spaceId: string): Promise<PrivatEmergencyContact[]> {
  const response = await apiClient.get<PrivatEmergencyContact[]>(`${BASE_URL}/spaces/${spaceId}/emergency/contacts`);
  return toCamelCase(response.data);
}

export async function createEmergencyContact(spaceId: string, data: PrivatEmergencyContactCreate): Promise<PrivatEmergencyContact> {
  const response = await apiClient.post<PrivatEmergencyContact>(`${BASE_URL}/spaces/${spaceId}/emergency/contacts`, toSnakeCase(data));
  return toCamelCase(response.data);
}

export async function updateEmergencyContact(contactId: string, data: PrivatEmergencyContactUpdate): Promise<PrivatEmergencyContact> {
  const response = await apiClient.patch<PrivatEmergencyContact>(`${BASE_URL}/emergency/contacts/${contactId}`, toSnakeCase(data));
  return toCamelCase(response.data);
}

export async function deleteEmergencyContact(contactId: string): Promise<void> {
  await apiClient.delete(`${BASE_URL}/emergency/contacts/${contactId}`);
}

export async function requestEmergencyAccess(data: PrivatEmergencyAccessRequestCreate): Promise<PrivatEmergencyAccessRequest> {
  const response = await apiClient.post<PrivatEmergencyAccessRequest>(`${BASE_URL}/emergency/request`, toSnakeCase(data));
  return toCamelCase(response.data);
}

export async function listEmergencyRequests(spaceId: string, status?: PrivatEmergencyAccessStatus): Promise<PrivatEmergencyAccessRequest[]> {
  const response = await apiClient.get<PrivatEmergencyAccessRequest[]>(`${BASE_URL}/spaces/${spaceId}/emergency/requests`, {
    params: status ? buildQueryParams({ statusFilter: status }) : undefined,
  });
  return toCamelCase(response.data);
}

export async function approveEmergencyRequest(requestId: string): Promise<PrivatEmergencyAccessRequest> {
  const response = await apiClient.post<PrivatEmergencyAccessRequest>(`${BASE_URL}/emergency/requests/${requestId}/approve`);
  return toCamelCase(response.data);
}

export async function denyEmergencyRequest(requestId: string, reason: string): Promise<PrivatEmergencyAccessRequest> {
  const response = await apiClient.post<PrivatEmergencyAccessRequest>(`${BASE_URL}/emergency/requests/${requestId}/deny`, null, {
    params: buildQueryParams({ reason }),
  });
  return toCamelCase(response.data);
}

export async function revokeEmergencyAccess(requestId: string): Promise<void> {
  await apiClient.post(`${BASE_URL}/emergency/requests/${requestId}/revoke`);
}

// ==================== Portfolio API ====================

export interface PortfolioSnapshot {
  id: string;
  spaceId: string;
  snapshotDate: string;
  totalRealEstate: number;
  totalVehicles: number;
  totalInvestments: number;
  totalCash: number;
  totalOtherAssets: number;
  totalMortgages: number;
  totalLoans: number;
  totalOtherLiabilities: number;
  totalAssets: number;
  totalLiabilities: number;
  netWorth: number;
  netWorthChangeAbsolute?: number;
  netWorthChangePercent?: number;
  debtToAssetsRatio: number;
  liquidityRatio: number;
  assetAllocation?: Record<string, number>;
  createdAt: string;
}

export interface FinancialGoal {
  id: string;
  spaceId: string;
  name: string;
  goalType: 'retirement' | 'education' | 'property' | 'debt_free' | 'emergency_fund' | 'custom';
  targetValue: number;
  targetDate: string;
  currentValue: number;
  progressPercent: number;
  monthlySavingsRequired?: number;
  monthsRemaining?: number;
  isOnTrack: boolean;
  projectedCompletionDate?: string;
  linkedAssets?: Record<string, unknown>;
  status: 'active' | 'paused' | 'completed' | 'cancelled';
  priority: number;
  createdAt: string;
  updatedAt: string;
}

export interface PortfolioDashboardResponse {
  snapshot: PortfolioSnapshot | null;
  historicalSnapshots: PortfolioSnapshot[];
  goals: FinancialGoal[];
  goalsSummary: FinancialGoalsSummary;
}

export interface FinancialGoalsSummary {
  totalGoals: number;
  activeGoals: number;
  completedGoals: number;
  onTrackCount: number;
  totalTargetValue: number;
  totalCurrentValue: number;
}

export interface FinancialGoalCreate {
  name: string;
  goalType: 'retirement' | 'education' | 'property' | 'debt_free' | 'emergency_fund' | 'custom';
  targetValue: number;
  targetDate: string;
  currentValue?: number;
  priority?: number;
  linkedAssets?: Record<string, unknown>;
}

export interface FinancialGoalUpdate {
  name?: string;
  goalType?: 'retirement' | 'education' | 'property' | 'debt_free' | 'emergency_fund' | 'custom';
  targetValue?: number;
  targetDate?: string;
  status?: 'active' | 'paused' | 'completed' | 'cancelled';
  priority?: number;
  linkedAssets?: Record<string, unknown>;
}

export interface GoalFilters {
  status?: string;
  goalType?: string;
}

/**
 * Holt das komplette Portfolio-Dashboard inkl. Snapshot und Zielen.
 */
export async function getPortfolioDashboard(spaceId: string): Promise<PortfolioDashboardResponse> {
  const response = await apiClient.get<PortfolioDashboardResponse>(
    `${BASE_URL}/spaces/${spaceId}/portfolio/dashboard`
  );
  return toCamelCase(response.data);
}

/**
 * Erstellt einen neuen Portfolio-Snapshot.
 */
export async function createPortfolioSnapshot(spaceId: string): Promise<PortfolioSnapshot> {
  const response = await apiClient.post<PortfolioSnapshot>(
    `${BASE_URL}/spaces/${spaceId}/portfolio/snapshot`
  );
  return toCamelCase(response.data);
}

/**
 * Listet historische Portfolio-Snapshots.
 */
export async function listPortfolioSnapshots(
  spaceId: string,
  limit: number = 12
): Promise<PortfolioSnapshot[]> {
  const response = await apiClient.get<PortfolioSnapshot[]>(
    `${BASE_URL}/spaces/${spaceId}/portfolio/snapshots`,
    { params: { limit } }
  );
  return toCamelCase(response.data);
}

// ==================== Financial Goals API ====================

/**
 * Listet alle finanziellen Ziele eines Space.
 */
export async function listFinancialGoals(
  spaceId: string,
  filters: GoalFilters = {}
): Promise<FinancialGoal[]> {
  const response = await apiClient.get<FinancialGoal[]>(
    `${BASE_URL}/spaces/${spaceId}/goals`,
    { params: buildQueryParams(filters) }
  );
  return toCamelCase(response.data);
}

/**
 * Erstellt ein neues finanzielles Ziel.
 */
export async function createFinancialGoal(
  spaceId: string,
  data: FinancialGoalCreate
): Promise<FinancialGoal> {
  const response = await apiClient.post<FinancialGoal>(
    `${BASE_URL}/spaces/${spaceId}/goals`,
    toSnakeCase(data)
  );
  return toCamelCase(response.data);
}

/**
 * Holt ein einzelnes Ziel.
 */
export async function getFinancialGoal(
  spaceId: string,
  goalId: string
): Promise<FinancialGoal> {
  const response = await apiClient.get<FinancialGoal>(
    `${BASE_URL}/spaces/${spaceId}/goals/${goalId}`
  );
  return toCamelCase(response.data);
}

/**
 * Aktualisiert ein Ziel.
 */
export async function updateFinancialGoal(
  spaceId: string,
  goalId: string,
  data: FinancialGoalUpdate
): Promise<FinancialGoal> {
  const response = await apiClient.patch<FinancialGoal>(
    `${BASE_URL}/spaces/${spaceId}/goals/${goalId}`,
    toSnakeCase(data)
  );
  return toCamelCase(response.data);
}

/**
 * Aktualisiert den Fortschritt eines Ziels.
 */
export async function updateGoalProgress(
  spaceId: string,
  goalId: string,
  newValue: number
): Promise<FinancialGoal> {
  const response = await apiClient.post<FinancialGoal>(
    `${BASE_URL}/spaces/${spaceId}/goals/${goalId}/progress`,
    { new_value: newValue }
  );
  return toCamelCase(response.data);
}

/**
 * Löscht ein Ziel.
 */
export async function deleteFinancialGoal(
  spaceId: string,
  goalId: string
): Promise<void> {
  await apiClient.delete(`${BASE_URL}/spaces/${spaceId}/goals/${goalId}`);
}

/**
 * Holt die Zusammenfassung aller Ziele.
 */
export async function getGoalsSummary(spaceId: string): Promise<FinancialGoalsSummary> {
  const response = await apiClient.get<FinancialGoalsSummary>(
    `${BASE_URL}/spaces/${spaceId}/goals/summary`
  );
  return toCamelCase(response.data);
}
