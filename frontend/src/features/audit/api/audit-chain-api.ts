/**
 * Audit Chain API Client
 *
 * API-Funktionen fuer den kryptografischen Audit-Trail
 * mit Merkle Tree Verifikation und Integritaets-Reports.
 */

import { useQuery, useMutation } from "@tanstack/react-query";
import { apiClient } from "@/lib/api/client";

// =============================================================================
// Types
// =============================================================================

export interface AuditChainStatus {
  status: "healthy" | "degraded";
  total_entries: number;
  root_hash: string;
  integrity_score: number;
  last_verified: string;
  violations_count: number;
}

export interface AuditViolation {
  entry_id: string;
  type: string;
  description: string;
  detected_at: string;
}

export interface IntegrityReport {
  total_entries: number;
  verified_entries: number;
  integrity_score: number;
  last_verified: string;
  violations: string[];
  root_hash: string;
}

export interface MerkleProofNode {
  hash: string;
  position: "left" | "right";
}

export interface MerkleProof {
  entry_hash: string;
  root_hash: string;
  proof_path: MerkleProofNode[];
  verified: boolean;
}

export interface VerifyProofRequest {
  entry_hash: string;
  root_hash: string;
  proof_path: MerkleProofNode[];
}

export interface VerifyProofResponse {
  verified: boolean;
  entry_hash: string;
  root_hash: string;
  timestamp: string;
}

export interface AuditEntry {
  id: string;
  user_id: string | null;
  user_email: string | null;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  ip_address: string | null;
  success: boolean;
  error_message: string | null;
  integrity_hash: string | null;
  created_at: string;
  metadata: Record<string, unknown>;
}

export interface AuditEntryListResponse {
  items: AuditEntry[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export interface AuditEntryFilters {
  page?: number;
  per_page?: number;
  action?: string;
  resource_type?: string;
  from_date?: string;
  to_date?: string;
  sort_order?: "asc" | "desc";
}

// =============================================================================
// API Functions
// =============================================================================

const CHAIN_API_BASE = "/audit-chain";
const ADMIN_AUDIT_API = "/admin/audit";

export async function getAuditChainStatus(): Promise<AuditChainStatus> {
  const response = await apiClient.get<AuditChainStatus>(
    `${CHAIN_API_BASE}/status`
  );
  return response.data;
}

export async function getIntegrityReport(): Promise<IntegrityReport> {
  const response = await apiClient.get<IntegrityReport>(
    `${CHAIN_API_BASE}/integrity-report`
  );
  return response.data;
}

export async function getMerkleProof(
  entryHash: string
): Promise<MerkleProof> {
  const response = await apiClient.get<MerkleProof>(
    `${CHAIN_API_BASE}/merkle-proof/${entryHash}`
  );
  return response.data;
}

export async function verifyProof(
  request: VerifyProofRequest
): Promise<VerifyProofResponse> {
  const response = await apiClient.post<VerifyProofResponse>(
    `${CHAIN_API_BASE}/verify`,
    request
  );
  return response.data;
}

export async function exportChain(
  fromDate?: string,
  toDate?: string
): Promise<Blob> {
  const params: Record<string, string> = {};
  if (fromDate) params.from_date = fromDate;
  if (toDate) params.to_date = toDate;

  const response = await apiClient.post(
    `${CHAIN_API_BASE}/export`,
    null,
    {
      params,
      responseType: "blob",
    }
  );
  return response.data;
}

export async function getAuditEntries(
  filters: AuditEntryFilters = {}
): Promise<AuditEntryListResponse> {
  const params = new URLSearchParams();

  if (filters.page) params.set("page", String(filters.page));
  if (filters.per_page) params.set("per_page", String(filters.per_page));
  if (filters.action) params.set("action", filters.action);
  if (filters.resource_type)
    params.set("resource_type", filters.resource_type);
  if (filters.from_date) params.set("from_date", filters.from_date);
  if (filters.to_date) params.set("to_date", filters.to_date);
  if (filters.sort_order) params.set("sort_order", filters.sort_order);

  const queryString = params.toString();
  const url = queryString
    ? `${ADMIN_AUDIT_API}/logs?${queryString}`
    : `${ADMIN_AUDIT_API}/logs`;

  const response = await apiClient.get<AuditEntryListResponse>(url);
  return response.data;
}

// =============================================================================
// React Query Hooks
// =============================================================================

export function useAuditChainStatus() {
  return useQuery({
    queryKey: ["audit-chain", "status"],
    queryFn: getAuditChainStatus,
    refetchInterval: 60_000,
    staleTime: 30_000,
  });
}

export function useIntegrityReport() {
  return useQuery({
    queryKey: ["audit-chain", "integrity-report"],
    queryFn: getIntegrityReport,
    refetchInterval: 120_000,
    staleTime: 60_000,
  });
}

export function useMerkleProof(entryHash: string | null) {
  return useQuery({
    queryKey: ["audit-chain", "merkle-proof", entryHash],
    queryFn: () => getMerkleProof(entryHash!),
    enabled: !!entryHash && entryHash.length === 64,
  });
}

export function useVerifyProof() {
  return useMutation({
    mutationFn: verifyProof,
  });
}

export function useExportChain() {
  return useMutation({
    mutationFn: ({
      fromDate,
      toDate,
    }: {
      fromDate?: string;
      toDate?: string;
    }) => exportChain(fromDate, toDate),
  });
}

export function useAuditEntries(filters: AuditEntryFilters = {}) {
  return useQuery({
    queryKey: ["audit-chain", "entries", filters],
    queryFn: () => getAuditEntries(filters),
    refetchInterval: 60_000,
  });
}
