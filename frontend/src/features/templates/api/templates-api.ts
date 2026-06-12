/**
 * Document Templates API
 *
 * API client and React Query hooks for document template management.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { UseQueryOptions } from '@tanstack/react-query';
import { fetchWithAuth } from '@/lib/api';
import type {
  Template,
  TemplateBrief,
  TemplateListResponse,
  TemplateListParams,
  TemplateCreateRequest,
  TemplateUpdateRequest,
  GeneratedDocument,
  GeneratedDocumentListResponse,
  GeneratedDocumentListParams,
  GenerateDocumentRequest,
  PreviewRequest,
  TemplateSnippet,
  SnippetCreateRequest,
  SnippetUpdateRequest,
  SnippetListParams,
  CategorySummary,
} from '../types/template-types';

// Relativ zur apiClient-baseURL ('/api/v1') — KEIN /api/v1-Prefix (sonst Doppel-Prefix /api/v1/api/v1/...)
const API_BASE = '/document-templates';

// =============================================================================
// Query Keys
// =============================================================================

export const templateKeys = {
  all: ['templates'] as const,
  lists: () => [...templateKeys.all, 'list'] as const,
  list: (params: TemplateListParams) => [...templateKeys.lists(), params] as const,
  brief: () => [...templateKeys.all, 'brief'] as const,
  details: () => [...templateKeys.all, 'detail'] as const,
  detail: (id: string) => [...templateKeys.details(), id] as const,
  categories: () => [...templateKeys.all, 'categories'] as const,
  generated: () => [...templateKeys.all, 'generated'] as const,
  generatedList: (params: GeneratedDocumentListParams) => [...templateKeys.generated(), 'list', params] as const,
  generatedDetail: (id: string) => [...templateKeys.generated(), 'detail', id] as const,
  snippets: () => [...templateKeys.all, 'snippets'] as const,
  snippetList: (params: SnippetListParams) => [...templateKeys.snippets(), 'list', params] as const,
  snippetDetail: (id: string) => [...templateKeys.snippets(), 'detail', id] as const,
};

// =============================================================================
// API Functions - Templates
// =============================================================================

export async function listTemplates(params: TemplateListParams = {}): Promise<TemplateListResponse> {
  const searchParams = new URLSearchParams();
  if (params.category) searchParams.set('category', params.category);
  if (params.is_active !== undefined) searchParams.set('is_active', params.is_active.toString());
  if (params.is_default !== undefined) searchParams.set('is_default', params.is_default.toString());
  if (params.search) searchParams.set('search', params.search);
  if (params.tags?.length) params.tags.forEach(tag => searchParams.append('tags', tag));
  if (params.offset !== undefined) searchParams.set('offset', params.offset.toString());
  if (params.limit !== undefined) searchParams.set('limit', params.limit.toString());

  const query = searchParams.toString();
  return fetchWithAuth<TemplateListResponse>(`${API_BASE}${query ? `?${query}` : ''}`);
}

export async function listBriefTemplates(): Promise<TemplateBrief[]> {
  return fetchWithAuth<TemplateBrief[]>(`${API_BASE}/brief`);
}

export async function getTemplate(id: string): Promise<Template> {
  return fetchWithAuth<Template>(`${API_BASE}/${id}`);
}

export async function createTemplate(data: TemplateCreateRequest): Promise<Template> {
  return fetchWithAuth<Template>(API_BASE, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateTemplate(id: string, data: TemplateUpdateRequest): Promise<Template> {
  return fetchWithAuth<Template>(`${API_BASE}/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

export async function deleteTemplate(id: string): Promise<void> {
  return fetchWithAuth<void>(`${API_BASE}/${id}`, {
    method: 'DELETE',
  });
}

export async function getCategorySummary(): Promise<CategorySummary[]> {
  return fetchWithAuth<CategorySummary[]>(`${API_BASE}/categories`);
}

// =============================================================================
// API Functions - Preview & Validation
// =============================================================================

export async function previewTemplate(id: string, data: PreviewRequest): Promise<string> {
  const response = await fetchWithAuth<{ html: string }>(`${API_BASE}/${id}/preview`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
  return response.html;
}

export async function validateTemplate(id: string, variables: Record<string, unknown>): Promise<{ valid: boolean; errors: string[] }> {
  return fetchWithAuth<{ valid: boolean; errors: string[] }>(`${API_BASE}/${id}/validate`, {
    method: 'POST',
    body: JSON.stringify({ variables }),
  });
}

// =============================================================================
// API Functions - Document Generation
// =============================================================================

export async function generateDocument(data: GenerateDocumentRequest): Promise<GeneratedDocument> {
  return fetchWithAuth<GeneratedDocument>(`${API_BASE}/generate`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function listGeneratedDocuments(params: GeneratedDocumentListParams = {}): Promise<GeneratedDocumentListResponse> {
  const searchParams = new URLSearchParams();
  if (params.template_id) searchParams.set('template_id', params.template_id);
  if (params.entity_id) searchParams.set('entity_id', params.entity_id);
  if (params.search) searchParams.set('search', params.search);
  if (params.offset !== undefined) searchParams.set('offset', params.offset.toString());
  if (params.limit !== undefined) searchParams.set('limit', params.limit.toString());

  const query = searchParams.toString();
  return fetchWithAuth<GeneratedDocumentListResponse>(`${API_BASE}/generated${query ? `?${query}` : ''}`);
}

export async function getGeneratedDocument(id: string): Promise<GeneratedDocument> {
  return fetchWithAuth<GeneratedDocument>(`${API_BASE}/generated/${id}`);
}

export async function downloadGeneratedDocument(id: string): Promise<Blob> {
  // Raw fetch geht NICHT durch die apiClient-baseURL -> voller Pfad inkl. /api/v1 noetig
  const response = await fetch(`/api/v1${API_BASE}/generated/${id}/download`, {
    credentials: 'include',
  });
  if (!response.ok) {
    throw new Error('Download fehlgeschlagen');
  }
  return response.blob();
}

// =============================================================================
// API Functions - Snippets
// =============================================================================

export async function listSnippets(params: SnippetListParams = {}): Promise<TemplateSnippet[]> {
  const searchParams = new URLSearchParams();
  if (params.category) searchParams.set('category', params.category);
  if (params.is_active !== undefined) searchParams.set('is_active', params.is_active.toString());
  if (params.search) searchParams.set('search', params.search);
  if (params.offset !== undefined) searchParams.set('offset', params.offset.toString());
  if (params.limit !== undefined) searchParams.set('limit', params.limit.toString());

  const query = searchParams.toString();
  return fetchWithAuth<TemplateSnippet[]>(`${API_BASE}/snippets${query ? `?${query}` : ''}`);
}

export async function getSnippet(id: string): Promise<TemplateSnippet> {
  return fetchWithAuth<TemplateSnippet>(`${API_BASE}/snippets/${id}`);
}

export async function createSnippet(data: SnippetCreateRequest): Promise<TemplateSnippet> {
  return fetchWithAuth<TemplateSnippet>(`${API_BASE}/snippets`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateSnippet(id: string, data: SnippetUpdateRequest): Promise<TemplateSnippet> {
  return fetchWithAuth<TemplateSnippet>(`${API_BASE}/snippets/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

export async function deleteSnippet(id: string): Promise<void> {
  return fetchWithAuth<void>(`${API_BASE}/snippets/${id}`, {
    method: 'DELETE',
  });
}

// =============================================================================
// React Query Hooks - Templates
// =============================================================================

export function useTemplates(params: TemplateListParams = {}, options?: UseQueryOptions<TemplateListResponse>) {
  return useQuery({
    queryKey: templateKeys.list(params),
    queryFn: () => listTemplates(params),
    ...options,
  });
}

export function useBriefTemplates(options?: UseQueryOptions<TemplateBrief[]>) {
  return useQuery({
    queryKey: templateKeys.brief(),
    queryFn: listBriefTemplates,
    ...options,
  });
}

export function useTemplate(id: string, options?: UseQueryOptions<Template>) {
  return useQuery({
    queryKey: templateKeys.detail(id),
    queryFn: () => getTemplate(id),
    enabled: !!id,
    ...options,
  });
}

export function useCategorySummary(options?: UseQueryOptions<CategorySummary[]>) {
  return useQuery({
    queryKey: templateKeys.categories(),
    queryFn: getCategorySummary,
    ...options,
  });
}

export function useCreateTemplate() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: createTemplate,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: templateKeys.all });
    },
  });
}

export function useUpdateTemplate() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: TemplateUpdateRequest }) => updateTemplate(id, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: templateKeys.detail(variables.id) });
      queryClient.invalidateQueries({ queryKey: templateKeys.lists() });
      queryClient.invalidateQueries({ queryKey: templateKeys.categories() });
    },
  });
}

export function useDeleteTemplate() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: deleteTemplate,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: templateKeys.all });
    },
  });
}

// =============================================================================
// React Query Hooks - Document Generation
// =============================================================================

export function useGeneratedDocuments(params: GeneratedDocumentListParams = {}, options?: UseQueryOptions<GeneratedDocumentListResponse>) {
  return useQuery({
    queryKey: templateKeys.generatedList(params),
    queryFn: () => listGeneratedDocuments(params),
    ...options,
  });
}

export function useGeneratedDocument(id: string, options?: UseQueryOptions<GeneratedDocument>) {
  return useQuery({
    queryKey: templateKeys.generatedDetail(id),
    queryFn: () => getGeneratedDocument(id),
    enabled: !!id,
    ...options,
  });
}

export function useGenerateDocument() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: generateDocument,
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: templateKeys.generated() });
      queryClient.invalidateQueries({ queryKey: templateKeys.detail(variables.template_id) });
    },
  });
}

export function usePreviewTemplate() {
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: PreviewRequest }) => previewTemplate(id, data),
  });
}

export function useValidateTemplate() {
  return useMutation({
    mutationFn: ({ id, variables }: { id: string; variables: Record<string, unknown> }) => validateTemplate(id, variables),
  });
}

// =============================================================================
// React Query Hooks - Snippets
// =============================================================================

export function useSnippets(params: SnippetListParams = {}, options?: UseQueryOptions<TemplateSnippet[]>) {
  return useQuery({
    queryKey: templateKeys.snippetList(params),
    queryFn: () => listSnippets(params),
    ...options,
  });
}

export function useSnippet(id: string, options?: UseQueryOptions<TemplateSnippet>) {
  return useQuery({
    queryKey: templateKeys.snippetDetail(id),
    queryFn: () => getSnippet(id),
    enabled: !!id,
    ...options,
  });
}

export function useCreateSnippet() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: createSnippet,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: templateKeys.snippets() });
    },
  });
}

export function useUpdateSnippet() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: SnippetUpdateRequest }) => updateSnippet(id, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: templateKeys.snippetDetail(variables.id) });
      queryClient.invalidateQueries({ queryKey: templateKeys.snippets() });
    },
  });
}

export function useDeleteSnippet() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: deleteSnippet,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: templateKeys.snippets() });
    },
  });
}
