import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

const API_BASE = '/api/v1/visual-builder';

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    credentials: 'include',
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Fehler: ${response.status}`);
  }
  return response.json();
}

// Types
export interface BlockDefinition {
  id: string;
  type: string;
  label: string;
  description: string;
  category: string;
  icon: string;
  config_schema: Record<string, unknown>;
  inputs: Array<{ id: string; label: string; type: string }>;
  outputs: Array<{ id: string; label: string; type: string }>;
}

export interface BlockCategory {
  id: string;
  label: string;
  description: string;
}

export interface WorkflowTemplate {
  id: string;
  name: string;
  description: string;
  category: string;
  blocks: VisualBlock[];
  edges: VisualEdge[];
}

export interface VisualBlock {
  id: string;
  type: string;
  label: string;
  config: Record<string, unknown>;
  position_x: number;
  position_y: number;
}

export interface VisualEdge {
  id: string;
  source_id: string;
  target_id: string;
  source_handle: string;
  target_handle: string;
  label?: string;
}

export interface WorkflowCreatePayload {
  name: string;
  description?: string;
  blocks: VisualBlock[];
  edges: VisualEdge[];
  variables?: Record<string, unknown>;
}

export interface WorkflowCreateResponse {
  workflow_id: string;
  name: string;
  message: string;
  validation_errors?: string[];
}

export interface SimulationPayload {
  blocks: VisualBlock[];
  edges: VisualEdge[];
  test_data?: Record<string, unknown>;
}

export interface SimulationResult {
  success: boolean;
  execution_path: string[];
  simulated_outputs: Record<string, unknown>;
  warnings?: string[];
  errors?: string[];
  duration_estimate_seconds: number;
}

// Hooks
export function useWorkflowBlocks(category?: string) {
  return useQuery<BlockDefinition[]>({
    queryKey: ['workflow-blocks', category],
    queryFn: async () => {
      const url = category
        ? `${API_BASE}/blocks?category=${encodeURIComponent(category)}`
        : `${API_BASE}/blocks`;
      return fetchJson<BlockDefinition[]>(url);
    },
  });
}

export function useWorkflowCategories() {
  return useQuery<BlockCategory[]>({
    queryKey: ['workflow-categories'],
    queryFn: () => fetchJson<BlockCategory[]>(`${API_BASE}/categories`),
  });
}

export function useWorkflowTemplates() {
  return useQuery<WorkflowTemplate[]>({
    queryKey: ['workflow-templates'],
    queryFn: () => fetchJson<WorkflowTemplate[]>(`${API_BASE}/templates`),
  });
}

export function useCreateWorkflow() {
  const queryClient = useQueryClient();

  return useMutation<WorkflowCreateResponse, Error, WorkflowCreatePayload>({
    mutationFn: (payload) =>
      fetchJson<WorkflowCreateResponse>(`${API_BASE}/create`, {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workflow-templates'] });
    },
  });
}

export function useUpdateWorkflow() {
  const queryClient = useQueryClient();

  return useMutation<
    WorkflowCreateResponse,
    Error,
    { workflowId: string; payload: WorkflowCreatePayload }
  >({
    mutationFn: ({ workflowId, payload }) =>
      fetchJson<WorkflowCreateResponse>(`${API_BASE}/${workflowId}`, {
        method: 'PUT',
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workflow-templates'] });
    },
  });
}

export function useSimulateWorkflow() {
  return useMutation<SimulationResult, Error, SimulationPayload>({
    mutationFn: (payload) =>
      fetchJson<SimulationResult>(`${API_BASE}/simulate`, {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
  });
}
