import { apiClient } from '@/lib/api/client';

export interface LifecycleEvent {
  id: string;
  event_type: string;
  event_data: Record<string, unknown>;
  timestamp: string;
  duration_ms: number | null;
  confidence: number | null;
  user_id: string | null;
  source_service: string | null;
}

export interface LifecycleResponse {
  document_id: string;
  events: LifecycleEvent[];
  total: number;
  limit: number;
  offset: number;
}

export interface LifecycleStats {
  document_id: string;
  total_events: number;
  total_processing_duration_ms: number;
  ocr: Record<string, unknown>;
  classification: Record<string, unknown>;
  entity_linking: Record<string, unknown>;
  modifications: Record<string, unknown>;
}

export async function fetchDocumentLifecycle(documentId: string): Promise<LifecycleResponse> {
  const response = await apiClient.get(`/documents/${documentId}/lineage`);
  return response.data;
}

export async function fetchDocumentLifecycleStats(documentId: string): Promise<LifecycleStats> {
  const response = await apiClient.get(`/documents/${documentId}/lineage/stats`);
  return response.data;
}
