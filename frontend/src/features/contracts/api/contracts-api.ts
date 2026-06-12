/**
 * Contract Management API
 *
 * API client and React Query hooks for contract management.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { UseQueryOptions } from '@tanstack/react-query';
import { fetchWithAuth } from '@/lib/api';
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
} from '../types/contract-types';

const API_BASE = '/contracts';

// =============================================================================
// Query Keys
// =============================================================================

export const contractKeys = {
  all: ['contracts'] as const,
  lists: () => [...contractKeys.all, 'list'] as const,
  list: (params: ContractListParams) => [...contractKeys.lists(), params] as const,
  details: () => [...contractKeys.all, 'detail'] as const,
  detail: (id: string) => [...contractKeys.details(), id] as const,
  timeline: (id: string) => [...contractKeys.detail(id), 'timeline'] as const,
  summary: () => [...contractKeys.all, 'summary'] as const,
  deadlines: (days: number) => [...contractKeys.all, 'deadlines', days] as const,
  renewalOptions: (contractId: string) => [...contractKeys.detail(contractId), 'renewals'] as const,
};

// =============================================================================
// API Functions
// =============================================================================

// Contract CRUD
export async function listContracts(params: ContractListParams = {}): Promise<ContractListResponse> {
  const searchParams = new URLSearchParams();
  if (params.status) searchParams.set('status', params.status);
  if (params.contract_type) searchParams.set('contract_type', params.contract_type);
  if (params.party_id) searchParams.set('party_id', params.party_id);
  if (params.expiring_within_days) searchParams.set('expiring_within_days', params.expiring_within_days.toString());
  if (params.search) searchParams.set('search', params.search);
  if (params.offset !== undefined) searchParams.set('offset', params.offset.toString());
  if (params.limit !== undefined) searchParams.set('limit', params.limit.toString());
  if (params.order_by) searchParams.set('order_by', params.order_by);
  if (params.order_dir) searchParams.set('order_dir', params.order_dir);

  const query = searchParams.toString();
  return fetchWithAuth<ContractListResponse>(`${API_BASE}${query ? `?${query}` : ''}`);
}

export async function getContract(id: string): Promise<ContractDetail> {
  return fetchWithAuth<ContractDetail>(`${API_BASE}/${id}`);
}

export async function createContract(data: ContractCreateRequest): Promise<Contract> {
  return fetchWithAuth<Contract>(API_BASE, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateContract(id: string, data: ContractUpdateRequest): Promise<Contract> {
  return fetchWithAuth<Contract>(`${API_BASE}/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

export async function deleteContract(id: string): Promise<void> {
  return fetchWithAuth<void>(`${API_BASE}/${id}`, {
    method: 'DELETE',
  });
}

// Summary and Deadlines
export async function getContractSummary(): Promise<ContractSummary> {
  return fetchWithAuth<ContractSummary>(`${API_BASE}/summary`);
}

export async function getUpcomingDeadlines(daysAhead: number = 90): Promise<DeadlineListResponse> {
  return fetchWithAuth<DeadlineListResponse>(`${API_BASE}/deadlines?days_ahead=${daysAhead}`);
}

export async function getContractTimeline(id: string): Promise<ContractTimeline> {
  return fetchWithAuth<ContractTimeline>(`${API_BASE}/${id}/timeline`);
}

// Milestones
export async function createMilestone(contractId: string, data: MilestoneCreateRequest): Promise<ContractMilestone> {
  return fetchWithAuth<ContractMilestone>(`${API_BASE}/${contractId}/milestones`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateMilestone(
  contractId: string,
  milestoneId: string,
  data: MilestoneUpdateRequest
): Promise<ContractMilestone> {
  return fetchWithAuth<ContractMilestone>(`${API_BASE}/${contractId}/milestones/${milestoneId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

export async function deleteMilestone(contractId: string, milestoneId: string): Promise<void> {
  return fetchWithAuth<void>(`${API_BASE}/${contractId}/milestones/${milestoneId}`, {
    method: 'DELETE',
  });
}

// Renewal Options
export async function listRenewalOptions(contractId: string): Promise<ContractRenewalOption[]> {
  return fetchWithAuth<ContractRenewalOption[]>(`${API_BASE}/${contractId}/renewal-options`);
}

export async function makeRenewalDecision(
  contractId: string,
  optionId: string,
  data: RenewalOptionDecision
): Promise<ContractRenewalOption> {
  return fetchWithAuth<ContractRenewalOption>(`${API_BASE}/${contractId}/renewal-options/${optionId}/decision`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// Amendments
export async function createAmendment(contractId: string, data: AmendmentCreateRequest): Promise<ContractAmendment> {
  return fetchWithAuth<ContractAmendment>(`${API_BASE}/${contractId}/amendments`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateAmendment(
  contractId: string,
  amendmentId: string,
  data: AmendmentUpdateRequest
): Promise<ContractAmendment> {
  return fetchWithAuth<ContractAmendment>(`${API_BASE}/${contractId}/amendments/${amendmentId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

export async function deleteAmendment(contractId: string, amendmentId: string): Promise<void> {
  return fetchWithAuth<void>(`${API_BASE}/${contractId}/amendments/${amendmentId}`, {
    method: 'DELETE',
  });
}

// =============================================================================
// React Query Hooks
// =============================================================================

// List Contracts
export function useContracts(params: ContractListParams = {}, options?: Omit<UseQueryOptions<ContractListResponse>, 'queryKey' | 'queryFn'>) {
  return useQuery({
    queryKey: contractKeys.list(params),
    queryFn: () => listContracts(params),
    ...options,
  });
}

// Get Single Contract
export function useContract(id: string, options?: Omit<UseQueryOptions<ContractDetail>, 'queryKey' | 'queryFn'>) {
  return useQuery({
    queryKey: contractKeys.detail(id),
    queryFn: () => getContract(id),
    enabled: !!id,
    ...options,
  });
}

// Get Contract Timeline
export function useContractTimeline(id: string, options?: Omit<UseQueryOptions<ContractTimeline>, 'queryKey' | 'queryFn'>) {
  return useQuery({
    queryKey: contractKeys.timeline(id),
    queryFn: () => getContractTimeline(id),
    enabled: !!id,
    ...options,
  });
}

// Get Summary
export function useContractSummary(options?: Omit<UseQueryOptions<ContractSummary>, 'queryKey' | 'queryFn'>) {
  return useQuery({
    queryKey: contractKeys.summary(),
    queryFn: getContractSummary,
    ...options,
  });
}

// Get Deadlines
export function useUpcomingDeadlines(daysAhead: number = 90, options?: Omit<UseQueryOptions<DeadlineListResponse>, 'queryKey' | 'queryFn'>) {
  return useQuery({
    queryKey: contractKeys.deadlines(daysAhead),
    queryFn: () => getUpcomingDeadlines(daysAhead),
    ...options,
  });
}

// Get Renewal Options
export function useRenewalOptions(contractId: string, options?: Omit<UseQueryOptions<ContractRenewalOption[]>, 'queryKey' | 'queryFn'>) {
  return useQuery({
    queryKey: contractKeys.renewalOptions(contractId),
    queryFn: () => listRenewalOptions(contractId),
    enabled: !!contractId,
    ...options,
  });
}

// Create Contract
export function useCreateContract() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: createContract,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: contractKeys.all });
    },
  });
}

// Update Contract
export function useUpdateContract() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: ContractUpdateRequest }) => updateContract(id, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: contractKeys.detail(variables.id) });
      queryClient.invalidateQueries({ queryKey: contractKeys.lists() });
      queryClient.invalidateQueries({ queryKey: contractKeys.summary() });
    },
  });
}

// Delete Contract
export function useDeleteContract() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: deleteContract,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: contractKeys.all });
    },
  });
}

// Create Milestone
export function useCreateMilestone() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ contractId, data }: { contractId: string; data: MilestoneCreateRequest }) =>
      createMilestone(contractId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: contractKeys.detail(variables.contractId) });
    },
  });
}

// Update Milestone
export function useUpdateMilestone() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      contractId,
      milestoneId,
      data,
    }: {
      contractId: string;
      milestoneId: string;
      data: MilestoneUpdateRequest;
    }) => updateMilestone(contractId, milestoneId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: contractKeys.detail(variables.contractId) });
    },
  });
}

// Delete Milestone
export function useDeleteMilestone() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ contractId, milestoneId }: { contractId: string; milestoneId: string }) =>
      deleteMilestone(contractId, milestoneId),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: contractKeys.detail(variables.contractId) });
    },
  });
}

// Renewal Decision
export function useRenewalDecision() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      contractId,
      optionId,
      data,
    }: {
      contractId: string;
      optionId: string;
      data: RenewalOptionDecision;
    }) => makeRenewalDecision(contractId, optionId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: contractKeys.detail(variables.contractId) });
      queryClient.invalidateQueries({ queryKey: contractKeys.renewalOptions(variables.contractId) });
      queryClient.invalidateQueries({ queryKey: contractKeys.summary() });
    },
  });
}

// Create Amendment
export function useCreateAmendment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ contractId, data }: { contractId: string; data: AmendmentCreateRequest }) =>
      createAmendment(contractId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: contractKeys.detail(variables.contractId) });
    },
  });
}

// Update Amendment
export function useUpdateAmendment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      contractId,
      amendmentId,
      data,
    }: {
      contractId: string;
      amendmentId: string;
      data: AmendmentUpdateRequest;
    }) => updateAmendment(contractId, amendmentId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: contractKeys.detail(variables.contractId) });
    },
  });
}

// Delete Amendment
export function useDeleteAmendment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ contractId, amendmentId }: { contractId: string; amendmentId: string }) =>
      deleteAmendment(contractId, amendmentId),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: contractKeys.detail(variables.contractId) });
    },
  });
}
