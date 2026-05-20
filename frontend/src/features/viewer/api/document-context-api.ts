import { apiClient } from '@/lib/api/client'
import type { DocumentContextData } from '../types/document-context-types'

export async function getDocumentContext(documentId: string): Promise<DocumentContextData> {
  const response = await apiClient.get<DocumentContextData>(`/documents/${documentId}/context`)
  return response.data
}
