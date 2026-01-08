/**
 * React Query Hooks für das Privat-Modul
 *
 * Bietet:
 * - Automatisches Caching
 * - Background Refetching
 * - Optimistic Updates
 * - Mutation Invalidation
 * - Error Handling
 */

import { useQuery, useMutation, useQueryClient, type UseQueryOptions } from '@tanstack/react-query';
import * as privatApi from '../api/privat-api';
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
  PrivatPropertyCreate,
  PrivatPropertyUpdate,
  PrivatPropertyWithDetails,
  PrivatPropertyListResponse,
  PrivatTenantCreate,
  PrivatTenant,
  PrivatRentalIncomeCreate,
  PrivatRentalIncome,
  PrivatVehicleCreate,
  PrivatVehicleUpdate,
  PrivatVehicleWithStats,
  PrivatVehicleListResponse,
  PrivatFuelLogCreate,
  PrivatFuelLog,
  PrivatFuelStatistics,
  PrivatInsuranceCreate,
  PrivatInsuranceUpdate,
  PrivatInsuranceWithDeadlines,
  PrivatInsuranceListResponse,
  PrivatLoanCreate,
  PrivatLoanUpdate,
  PrivatLoanWithStats,
  PrivatLoanListResponse,
  PrivatInvestmentCreate,
  PrivatInvestmentUpdate,
  PrivatInvestmentWithStats,
  PrivatInvestmentListResponse,
  PrivatPortfolioBreakdown,
  PrivatDeadlineCreate,
  PrivatDeadlineUpdate,
  PrivatDeadlineWithStatus,
  PrivatDeadlineListResponse,
  PrivatDeadlineWidget,
  PrivatEmergencyContactCreate,
  PrivatEmergencyContactUpdate,
  PrivatEmergencyContact,
  PrivatEmergencyAccessRequestCreate,
  PrivatEmergencyAccessRequest,
  PrivatDashboardStats,
  PrivatFinancialSummary,
} from '@/types/privat';

// ==================== Query Keys ====================

export const privatQueryKeys = {
  all: ['privat'] as const,
  // Dashboard
  dashboard: () => [...privatQueryKeys.all, 'dashboard'] as const,
  financialSummary: (spaceId: string) => [...privatQueryKeys.all, 'financial-summary', spaceId] as const,
  // Spaces
  spaces: () => [...privatQueryKeys.all, 'spaces'] as const,
  space: (spaceId: string) => [...privatQueryKeys.spaces(), spaceId] as const,
  spaceAccess: (spaceId: string) => [...privatQueryKeys.space(spaceId), 'access'] as const,
  // Folders
  folders: (spaceId: string) => [...privatQueryKeys.space(spaceId), 'folders'] as const,
  // Documents
  documents: (spaceId: string) => [...privatQueryKeys.space(spaceId), 'documents'] as const,
  documentsList: (spaceId: string, filters: privatApi.DocumentFilters) =>
    [...privatQueryKeys.documents(spaceId), filters] as const,
  document: (documentId: string) => [...privatQueryKeys.all, 'document', documentId] as const,
  // Properties
  properties: (spaceId: string) => [...privatQueryKeys.space(spaceId), 'properties'] as const,
  propertiesList: (spaceId: string, filters: privatApi.PropertyFilters) =>
    [...privatQueryKeys.properties(spaceId), filters] as const,
  property: (propertyId: string) => [...privatQueryKeys.all, 'property', propertyId] as const,
  tenants: (propertyId: string) => [...privatQueryKeys.property(propertyId), 'tenants'] as const,
  // Vehicles
  vehicles: (spaceId: string) => [...privatQueryKeys.space(spaceId), 'vehicles'] as const,
  vehiclesList: (spaceId: string, filters: privatApi.VehicleFilters) =>
    [...privatQueryKeys.vehicles(spaceId), filters] as const,
  vehicle: (vehicleId: string) => [...privatQueryKeys.all, 'vehicle', vehicleId] as const,
  fuelLogs: (vehicleId: string, filters?: privatApi.FuelLogFilters) =>
    [...privatQueryKeys.vehicle(vehicleId), 'fuel', filters] as const,
  fuelStats: (vehicleId: string) => [...privatQueryKeys.vehicle(vehicleId), 'fuel-stats'] as const,
  // Insurances
  insurances: (spaceId: string) => [...privatQueryKeys.space(spaceId), 'insurances'] as const,
  insurancesList: (spaceId: string, filters: privatApi.InsuranceFilters) =>
    [...privatQueryKeys.insurances(spaceId), filters] as const,
  insurance: (insuranceId: string) => [...privatQueryKeys.all, 'insurance', insuranceId] as const,
  // Loans
  loans: (spaceId: string) => [...privatQueryKeys.space(spaceId), 'loans'] as const,
  loansList: (spaceId: string, filters: privatApi.LoanFilters) =>
    [...privatQueryKeys.loans(spaceId), filters] as const,
  // Investments
  investments: (spaceId: string) => [...privatQueryKeys.space(spaceId), 'investments'] as const,
  investmentsList: (spaceId: string, filters: privatApi.InvestmentFilters) =>
    [...privatQueryKeys.investments(spaceId), filters] as const,
  portfolio: (spaceId: string) => [...privatQueryKeys.investments(spaceId), 'portfolio'] as const,
  // Deadlines
  deadlines: (spaceId: string) => [...privatQueryKeys.space(spaceId), 'deadlines'] as const,
  deadlinesList: (spaceId: string, filters: privatApi.DeadlineFilters) =>
    [...privatQueryKeys.deadlines(spaceId), filters] as const,
  deadlineWidget: (spaceId: string) => [...privatQueryKeys.deadlines(spaceId), 'widget'] as const,
  // Emergency
  emergencyContacts: (spaceId: string) => [...privatQueryKeys.space(spaceId), 'emergency', 'contacts'] as const,
  emergencyRequests: (spaceId: string) => [...privatQueryKeys.space(spaceId), 'emergency', 'requests'] as const,
};

// ==================== Dashboard Hooks ====================

export function useDashboardStats(
  options?: Omit<UseQueryOptions<PrivatDashboardStats>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: privatQueryKeys.dashboard(),
    queryFn: privatApi.getDashboardStats,
    staleTime: 30 * 1000, // 30 Sekunden
    ...options,
  });
}

export function useFinancialSummary(
  spaceId: string,
  options?: Omit<UseQueryOptions<PrivatFinancialSummary>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: privatQueryKeys.financialSummary(spaceId),
    queryFn: () => privatApi.getFinancialSummary(spaceId),
    enabled: !!spaceId,
    staleTime: 60 * 1000, // 1 Minute
    ...options,
  });
}

// ==================== Space Hooks ====================

export function useSpaces(
  options?: Omit<UseQueryOptions<PrivatSpaceWithStats[]>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: privatQueryKeys.spaces(),
    queryFn: privatApi.listSpaces,
    staleTime: 60 * 1000,
    ...options,
  });
}

export function useSpace(
  spaceId: string,
  options?: Omit<UseQueryOptions<PrivatSpaceWithStats>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: privatQueryKeys.space(spaceId),
    queryFn: () => privatApi.getSpace(spaceId),
    enabled: !!spaceId,
    ...options,
  });
}

/**
 * Hook um den Standard-Bereich (persönlicher Bereich) zu ermitteln.
 * Nützlich wenn kein spaceId in der URL vorhanden ist.
 */
export function useDefaultSpace() {
  const { data: spaces, isLoading, error } = useSpaces();

  // Finde den ersten persönlichen Bereich
  const defaultSpace = spaces?.find((s) => s.spaceType === 'personal') ?? spaces?.[0];

  return {
    defaultSpaceId: defaultSpace?.id,
    defaultSpace,
    isLoading,
    error,
    hasSpaces: (spaces?.length ?? 0) > 0,
  };
}

export function useCreateSpace() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: PrivatSpaceCreate) => privatApi.createSpace(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.spaces() });
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.dashboard() });
    },
  });
}

export function useUpdateSpace() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ spaceId, data }: { spaceId: string; data: PrivatSpaceUpdate }) =>
      privatApi.updateSpace(spaceId, data),
    onSuccess: (_, { spaceId }) => {
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.space(spaceId) });
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.spaces() });
    },
  });
}

export function useDeleteSpace() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (spaceId: string) => privatApi.deleteSpace(spaceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.spaces() });
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.dashboard() });
    },
  });
}

// ==================== Space Access Hooks ====================

export function useSpaceAccess(
  spaceId: string,
  options?: Omit<UseQueryOptions<PrivatSpaceAccess[]>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: privatQueryKeys.spaceAccess(spaceId),
    queryFn: () => privatApi.listAccess(spaceId),
    enabled: !!spaceId,
    ...options,
  });
}

export function useGrantAccess() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ spaceId, data }: { spaceId: string; data: PrivatSpaceAccessCreate }) =>
      privatApi.grantAccess(spaceId, data),
    onSuccess: (_, { spaceId }) => {
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.spaceAccess(spaceId) });
    },
  });
}

export function useRevokeAccess() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ spaceId, userId }: { spaceId: string; userId: string }) =>
      privatApi.revokeAccess(spaceId, userId),
    onSuccess: (_, { spaceId }) => {
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.spaceAccess(spaceId) });
    },
  });
}

// ==================== Folder Hooks ====================

export function useFolderTree(
  spaceId: string,
  options?: Omit<UseQueryOptions<PrivatFolderTree[]>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: privatQueryKeys.folders(spaceId),
    queryFn: () => privatApi.getFolderTree(spaceId),
    enabled: !!spaceId,
    ...options,
  });
}

export function useCreateFolder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ spaceId, data }: { spaceId: string; data: PrivatFolderCreate }) =>
      privatApi.createFolder(spaceId, data),
    onSuccess: (_, { spaceId }) => {
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.folders(spaceId) });
    },
  });
}

export function useUpdateFolder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ folderId, data, spaceId }: { folderId: string; data: PrivatFolderUpdate; spaceId: string }) =>
      privatApi.updateFolder(folderId, data),
    onSuccess: (_, { spaceId }) => {
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.folders(spaceId) });
    },
  });
}

export function useMoveFolder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ folderId, newParentId, spaceId }: { folderId: string; newParentId?: string; spaceId: string }) =>
      privatApi.moveFolder(folderId, newParentId),
    onSuccess: (_, { spaceId }) => {
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.folders(spaceId) });
    },
  });
}

export function useDeleteFolder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ folderId, recursive, spaceId }: { folderId: string; recursive?: boolean; spaceId: string }) =>
      privatApi.deleteFolder(folderId, recursive),
    onSuccess: (_, { spaceId }) => {
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.folders(spaceId) });
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.documents(spaceId) });
    },
  });
}

// ==================== Document Hooks ====================

export function useDocuments(
  spaceId: string,
  filters: privatApi.DocumentFilters = {},
  options?: Omit<UseQueryOptions<PrivatDocumentListResponse>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: privatQueryKeys.documentsList(spaceId, filters),
    queryFn: () => privatApi.listDocuments(spaceId, filters),
    enabled: !!spaceId,
    ...options,
  });
}

export function useDocument(
  documentId: string,
  options?: Omit<UseQueryOptions<PrivatDocument>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: privatQueryKeys.document(documentId),
    queryFn: () => privatApi.getDocument(documentId),
    enabled: !!documentId,
    ...options,
  });
}

export function useCreateDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ spaceId, data, password }: { spaceId: string; data: PrivatDocumentCreate; password?: string }) =>
      privatApi.createDocument(spaceId, data, password),
    onSuccess: (result, { spaceId }) => {
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.documents(spaceId) });
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.space(spaceId) });
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.dashboard() });
    },
  });
}

export function useUpdateDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ documentId, data, spaceId }: { documentId: string; data: PrivatDocumentUpdate; spaceId: string }) =>
      privatApi.updateDocument(documentId, data),
    onSuccess: (result, { documentId, spaceId }) => {
      queryClient.setQueryData(privatQueryKeys.document(documentId), result);
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.documents(spaceId) });
    },
  });
}

export function useDeleteDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ documentId, spaceId }: { documentId: string; spaceId: string }) =>
      privatApi.deleteDocument(documentId),
    onSuccess: (_, { documentId, spaceId }) => {
      queryClient.removeQueries({ queryKey: privatQueryKeys.document(documentId) });
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.documents(spaceId) });
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.space(spaceId) });
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.dashboard() });
    },
  });
}

// ==================== Property Hooks ====================

export function useProperties(
  spaceId: string,
  filters: privatApi.PropertyFilters = {},
  options?: Omit<UseQueryOptions<PrivatPropertyListResponse>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: privatQueryKeys.propertiesList(spaceId, filters),
    queryFn: () => privatApi.listProperties(spaceId, filters),
    enabled: !!spaceId,
    ...options,
  });
}

export function useProperty(
  propertyId: string,
  options?: Omit<UseQueryOptions<PrivatPropertyWithDetails>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: privatQueryKeys.property(propertyId),
    queryFn: () => privatApi.getProperty(propertyId),
    enabled: !!propertyId,
    ...options,
  });
}

export function useCreateProperty() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ spaceId, data }: { spaceId: string; data: PrivatPropertyCreate }) =>
      privatApi.createProperty(spaceId, data),
    onSuccess: (_, { spaceId }) => {
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.properties(spaceId) });
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.financialSummary(spaceId) });
    },
  });
}

export function useUpdateProperty() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ propertyId, data, spaceId }: { propertyId: string; data: PrivatPropertyUpdate; spaceId: string }) =>
      privatApi.updateProperty(propertyId, data),
    onSuccess: (result, { propertyId, spaceId }) => {
      queryClient.setQueryData(privatQueryKeys.property(propertyId), result);
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.properties(spaceId) });
    },
  });
}

export function useDeleteProperty() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ propertyId, spaceId }: { propertyId: string; spaceId: string }) =>
      privatApi.deleteProperty(propertyId),
    onSuccess: (_, { propertyId, spaceId }) => {
      queryClient.removeQueries({ queryKey: privatQueryKeys.property(propertyId) });
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.properties(spaceId) });
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.financialSummary(spaceId) });
    },
  });
}

// ==================== Tenant Hooks ====================

export function useTenants(
  propertyId: string,
  activeOnly = true,
  options?: Omit<UseQueryOptions<PrivatTenant[]>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: [...privatQueryKeys.tenants(propertyId), activeOnly],
    queryFn: () => privatApi.listTenants(propertyId, activeOnly),
    enabled: !!propertyId,
    ...options,
  });
}

export function useCreateTenant() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ propertyId, data }: { propertyId: string; data: PrivatTenantCreate }) =>
      privatApi.createTenant(propertyId, data),
    onSuccess: (_, { propertyId }) => {
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.tenants(propertyId) });
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.property(propertyId) });
    },
  });
}

export function useRecordRentalIncome() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ tenantId, data, propertyId }: { tenantId: string; data: PrivatRentalIncomeCreate; propertyId: string }) =>
      privatApi.recordRentalIncome(tenantId, data),
    onSuccess: (_, { propertyId }) => {
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.property(propertyId) });
    },
  });
}

// ==================== Vehicle Hooks ====================

export function useVehicles(
  spaceId: string,
  filters: privatApi.VehicleFilters = {},
  options?: Omit<UseQueryOptions<PrivatVehicleListResponse>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: privatQueryKeys.vehiclesList(spaceId, filters),
    queryFn: () => privatApi.listVehicles(spaceId, filters),
    enabled: !!spaceId,
    ...options,
  });
}

export function useVehicle(
  vehicleId: string,
  options?: Omit<UseQueryOptions<PrivatVehicleWithStats>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: privatQueryKeys.vehicle(vehicleId),
    queryFn: () => privatApi.getVehicle(vehicleId),
    enabled: !!vehicleId,
    ...options,
  });
}

export function useCreateVehicle() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ spaceId, data }: { spaceId: string; data: PrivatVehicleCreate }) =>
      privatApi.createVehicle(spaceId, data),
    onSuccess: (_, { spaceId }) => {
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.vehicles(spaceId) });
    },
  });
}

export function useUpdateVehicle() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ vehicleId, data, spaceId }: { vehicleId: string; data: PrivatVehicleUpdate; spaceId: string }) =>
      privatApi.updateVehicle(vehicleId, data),
    onSuccess: (result, { vehicleId, spaceId }) => {
      queryClient.setQueryData(privatQueryKeys.vehicle(vehicleId), result);
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.vehicles(spaceId) });
    },
  });
}

export function useDeleteVehicle() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ vehicleId, spaceId }: { vehicleId: string; spaceId: string }) =>
      privatApi.deleteVehicle(vehicleId),
    onSuccess: (_, { vehicleId, spaceId }) => {
      queryClient.removeQueries({ queryKey: privatQueryKeys.vehicle(vehicleId) });
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.vehicles(spaceId) });
    },
  });
}

// ==================== Fuel Log Hooks ====================

export function useFuelLogs(
  vehicleId: string,
  filters: privatApi.FuelLogFilters = {},
  options?: Omit<UseQueryOptions<PrivatFuelLog[]>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: privatQueryKeys.fuelLogs(vehicleId, filters),
    queryFn: () => privatApi.listFuelLogs(vehicleId, filters),
    enabled: !!vehicleId,
    ...options,
  });
}

export function useFuelStatistics(
  vehicleId: string,
  options?: Omit<UseQueryOptions<PrivatFuelStatistics>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: privatQueryKeys.fuelStats(vehicleId),
    queryFn: () => privatApi.getFuelStatistics(vehicleId),
    enabled: !!vehicleId,
    ...options,
  });
}

export function useCreateFuelLog() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ vehicleId, data }: { vehicleId: string; data: PrivatFuelLogCreate }) =>
      privatApi.createFuelLog(vehicleId, data),
    onSuccess: (_, { vehicleId }) => {
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.vehicle(vehicleId) });
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.fuelLogs(vehicleId) });
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.fuelStats(vehicleId) });
    },
  });
}

// ==================== Insurance Hooks ====================

export function useInsurances(
  spaceId: string,
  filters: privatApi.InsuranceFilters = {},
  options?: Omit<UseQueryOptions<PrivatInsuranceListResponse>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: privatQueryKeys.insurancesList(spaceId, filters),
    queryFn: () => privatApi.listInsurances(spaceId, filters),
    enabled: !!spaceId,
    ...options,
  });
}

export function useInsurance(
  insuranceId: string,
  options?: Omit<UseQueryOptions<PrivatInsuranceWithDeadlines>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: privatQueryKeys.insurance(insuranceId),
    queryFn: () => privatApi.getInsurance(insuranceId),
    enabled: !!insuranceId,
    ...options,
  });
}

export function useCreateInsurance() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ spaceId, data }: { spaceId: string; data: PrivatInsuranceCreate }) =>
      privatApi.createInsurance(spaceId, data),
    onSuccess: (_, { spaceId }) => {
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.insurances(spaceId) });
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.deadlines(spaceId) });
    },
  });
}

export function useUpdateInsurance() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ insuranceId, data, spaceId }: { insuranceId: string; data: PrivatInsuranceUpdate; spaceId: string }) =>
      privatApi.updateInsurance(insuranceId, data),
    onSuccess: (_, { spaceId }) => {
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.insurances(spaceId) });
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.deadlines(spaceId) });
    },
  });
}

export function useDeleteInsurance() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ insuranceId, spaceId }: { insuranceId: string; spaceId: string }) =>
      privatApi.deleteInsurance(insuranceId),
    onSuccess: (_, { spaceId }) => {
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.insurances(spaceId) });
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.deadlines(spaceId) });
    },
  });
}

// ==================== Loan Hooks ====================

export function useLoans(
  spaceId: string,
  filters: privatApi.LoanFilters = {},
  options?: Omit<UseQueryOptions<PrivatLoanListResponse>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: privatQueryKeys.loansList(spaceId, filters),
    queryFn: () => privatApi.listLoans(spaceId, filters),
    enabled: !!spaceId,
    ...options,
  });
}

export function useCreateLoan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ spaceId, data }: { spaceId: string; data: PrivatLoanCreate }) =>
      privatApi.createLoan(spaceId, data),
    onSuccess: (_, { spaceId }) => {
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.loans(spaceId) });
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.financialSummary(spaceId) });
    },
  });
}

export function useUpdateLoan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ loanId, data, spaceId }: { loanId: string; data: PrivatLoanUpdate; spaceId: string }) =>
      privatApi.updateLoan(loanId, data),
    onSuccess: (_, { spaceId }) => {
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.loans(spaceId) });
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.financialSummary(spaceId) });
    },
  });
}

export function useRecordLoanPayment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ loanId, amount, paymentDate, spaceId }: { loanId: string; amount: number; paymentDate?: string; spaceId: string }) =>
      privatApi.recordLoanPayment(loanId, amount, paymentDate),
    onSuccess: (_, { spaceId }) => {
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.loans(spaceId) });
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.financialSummary(spaceId) });
    },
  });
}

export function useDeleteLoan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ loanId, spaceId }: { loanId: string; spaceId: string }) =>
      privatApi.deleteLoan(loanId),
    onSuccess: (_, { spaceId }) => {
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.loans(spaceId) });
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.financialSummary(spaceId) });
    },
  });
}

// ==================== Investment Hooks ====================

export function useInvestments(
  spaceId: string,
  filters: privatApi.InvestmentFilters = {},
  options?: Omit<UseQueryOptions<PrivatInvestmentListResponse>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: privatQueryKeys.investmentsList(spaceId, filters),
    queryFn: () => privatApi.listInvestments(spaceId, filters),
    enabled: !!spaceId,
    ...options,
  });
}

export function usePortfolioBreakdown(
  spaceId: string,
  options?: Omit<UseQueryOptions<PrivatPortfolioBreakdown>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: privatQueryKeys.portfolio(spaceId),
    queryFn: () => privatApi.getPortfolioBreakdown(spaceId),
    enabled: !!spaceId,
    staleTime: 60 * 1000,
    ...options,
  });
}

export function useCreateInvestment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ spaceId, data }: { spaceId: string; data: PrivatInvestmentCreate }) =>
      privatApi.createInvestment(spaceId, data),
    onSuccess: (_, { spaceId }) => {
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.investments(spaceId) });
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.portfolio(spaceId) });
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.financialSummary(spaceId) });
    },
  });
}

export function useUpdateInvestment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ investmentId, data, spaceId }: { investmentId: string; data: PrivatInvestmentUpdate; spaceId: string }) =>
      privatApi.updateInvestment(investmentId, data),
    onSuccess: (_, { spaceId }) => {
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.investments(spaceId) });
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.portfolio(spaceId) });
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.financialSummary(spaceId) });
    },
  });
}

export function useUpdateInvestmentValue() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ investmentId, newValue, spaceId }: { investmentId: string; newValue: number; spaceId: string }) =>
      privatApi.updateInvestmentValue(investmentId, newValue),
    onSuccess: (_, { spaceId }) => {
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.investments(spaceId) });
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.portfolio(spaceId) });
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.financialSummary(spaceId) });
    },
  });
}

export function useDeleteInvestment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ investmentId, spaceId }: { investmentId: string; spaceId: string }) =>
      privatApi.deleteInvestment(investmentId),
    onSuccess: (_, { spaceId }) => {
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.investments(spaceId) });
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.portfolio(spaceId) });
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.financialSummary(spaceId) });
    },
  });
}

// ==================== Deadline Hooks ====================

export function useDeadlines(
  spaceId: string,
  filters: privatApi.DeadlineFilters = {},
  options?: Omit<UseQueryOptions<PrivatDeadlineListResponse>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: privatQueryKeys.deadlinesList(spaceId, filters),
    queryFn: () => privatApi.listDeadlines(spaceId, filters),
    enabled: !!spaceId,
    ...options,
  });
}

export function useDeadlineWidget(
  spaceId: string,
  options?: Omit<UseQueryOptions<PrivatDeadlineWidget>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: privatQueryKeys.deadlineWidget(spaceId),
    queryFn: () => privatApi.getDeadlineWidget(spaceId),
    enabled: !!spaceId,
    staleTime: 30 * 1000,
    ...options,
  });
}

export function useCreateDeadline() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ spaceId, data }: { spaceId: string; data: PrivatDeadlineCreate }) =>
      privatApi.createDeadline(spaceId, data),
    onSuccess: (_, { spaceId }) => {
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.deadlines(spaceId) });
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.dashboard() });
    },
  });
}

export function useUpdateDeadline() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ deadlineId, data, spaceId }: { deadlineId: string; data: PrivatDeadlineUpdate; spaceId: string }) =>
      privatApi.updateDeadline(deadlineId, data),
    onSuccess: (_, { spaceId }) => {
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.deadlines(spaceId) });
    },
  });
}

export function useCompleteDeadline() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ deadlineId, spaceId }: { deadlineId: string; spaceId: string }) =>
      privatApi.completeDeadline(deadlineId),
    onSuccess: (_, { spaceId }) => {
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.deadlines(spaceId) });
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.dashboard() });
    },
  });
}

export function useDeleteDeadline() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ deadlineId, spaceId }: { deadlineId: string; spaceId: string }) =>
      privatApi.deleteDeadline(deadlineId),
    onSuccess: (_, { spaceId }) => {
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.deadlines(spaceId) });
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.dashboard() });
    },
  });
}

// ==================== Emergency Access Hooks ====================

export function useEmergencyContacts(
  spaceId: string,
  options?: Omit<UseQueryOptions<PrivatEmergencyContact[]>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: privatQueryKeys.emergencyContacts(spaceId),
    queryFn: () => privatApi.listEmergencyContacts(spaceId),
    enabled: !!spaceId,
    ...options,
  });
}

export function useCreateEmergencyContact() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ spaceId, data }: { spaceId: string; data: PrivatEmergencyContactCreate }) =>
      privatApi.createEmergencyContact(spaceId, data),
    onSuccess: (_, { spaceId }) => {
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.emergencyContacts(spaceId) });
    },
  });
}

export function useUpdateEmergencyContact() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ contactId, data, spaceId }: { contactId: string; data: PrivatEmergencyContactUpdate; spaceId: string }) =>
      privatApi.updateEmergencyContact(contactId, data),
    onSuccess: (_, { spaceId }) => {
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.emergencyContacts(spaceId) });
    },
  });
}

export function useDeleteEmergencyContact() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ contactId, spaceId }: { contactId: string; spaceId: string }) =>
      privatApi.deleteEmergencyContact(contactId),
    onSuccess: (_, { spaceId }) => {
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.emergencyContacts(spaceId) });
    },
  });
}

export function useEmergencyRequests(
  spaceId: string,
  status?: 'pending' | 'approved' | 'denied' | 'expired' | 'revoked',
  options?: Omit<UseQueryOptions<PrivatEmergencyAccessRequest[]>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: [...privatQueryKeys.emergencyRequests(spaceId), status],
    queryFn: () => privatApi.listEmergencyRequests(spaceId, status),
    enabled: !!spaceId,
    ...options,
  });
}

export function useRequestEmergencyAccess() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: PrivatEmergencyAccessRequestCreate) =>
      privatApi.requestEmergencyAccess(data),
    onSuccess: () => {
      // Invalidate all emergency requests queries
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.all });
    },
  });
}

export function useDenyEmergencyRequest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ requestId, reason, spaceId }: { requestId: string; reason: string; spaceId: string }) =>
      privatApi.denyEmergencyRequest(requestId, reason),
    onSuccess: (_, { spaceId }) => {
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.emergencyRequests(spaceId) });
    },
  });
}

export function useRevokeEmergencyAccess() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ requestId, spaceId }: { requestId: string; spaceId: string }) =>
      privatApi.revokeEmergencyAccess(requestId),
    onSuccess: (_, { spaceId }) => {
      queryClient.invalidateQueries({ queryKey: privatQueryKeys.emergencyRequests(spaceId) });
    },
  });
}
