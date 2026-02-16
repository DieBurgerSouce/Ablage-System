/**
 * Annotations API Client
 *
 * API-Funktionen fuer Dokument-Annotationen (Bounding Boxes, Kommentare).
 * Backend-Endpunkte: /api/v1/annotations/*
 */

import { apiClient } from '@/lib/api/client';

// ==================== Types ====================

export interface AnnotationPosition {
  x: number;
  y: number;
  width: number;
  height: number;
}

export type AnnotationType = 'comment' | 'highlight' | 'drawing' | 'approval' | 'rejection';

export interface Annotation {
  id: string;
  document_id: string;
  user_id: string;
  user_name?: string;
  annotation_type: AnnotationType;
  content: string;
  page: number;
  position: AnnotationPosition;
  svg_data?: string;
  parent_annotation_id?: string;
  mentioned_user_ids: string[];
  is_resolved: boolean;
  created_at: string;
  updated_at?: string;
}

export interface AnnotationCreatePayload {
  document_id: string;
  annotation_type: AnnotationType;
  content: string;
  page_number: number;
  position?: AnnotationPosition;
  parent_annotation_id?: string;
  mentioned_user_ids?: string[];
}

export interface AnnotationUpdatePayload {
  content?: string;
  is_resolved?: boolean;
}

// ==================== API Functions ====================

export async function getAnnotations(documentId: string): Promise<Annotation[]> {
  const response = await apiClient.get<Annotation[]>(
    `/annotations/document/${documentId}`
  );
  return response.data;
}

export async function createAnnotation(payload: AnnotationCreatePayload): Promise<Annotation> {
  const response = await apiClient.post<Annotation>('/annotations', payload);
  return response.data;
}

export async function updateAnnotation(
  id: string,
  payload: AnnotationUpdatePayload
): Promise<Annotation> {
  const response = await apiClient.patch<Annotation>(`/annotations/${id}`, payload);
  return response.data;
}

export async function deleteAnnotation(id: string): Promise<void> {
  await apiClient.delete(`/annotations/${id}`);
}
