/**
 * useActivity - Hook fuer Dokumenten-Aktivitaetsverlauf
 *
 * Laedt die Aktivitaetshistorie eines Dokuments.
 */

import { useQuery } from '@tanstack/react-query';
import type { Activity, ActivitiesResponse, ActivityType } from '../types/collaboration.types';

// ==================== Mock Data ====================

const ACTIVITY_DESCRIPTIONS: Record<ActivityType, string> = {
  document_created: 'hat das Dokument erstellt',
  document_updated: 'hat das Dokument aktualisiert',
  document_viewed: 'hat das Dokument angesehen',
  document_downloaded: 'hat das Dokument heruntergeladen',
  comment_added: 'hat einen Kommentar hinzugefuegt',
  comment_replied: 'hat auf einen Kommentar geantwortet',
  status_changed: 'hat den Status geaendert',
  tags_changed: 'hat die Tags geaendert',
  metadata_updated: 'hat die Metadaten aktualisiert',
  document_shared: 'hat das Dokument geteilt',
};

const MOCK_ACTIVITIES: Activity[] = [
  {
    id: 'activity-1',
    documentId: 'doc-1',
    userId: 'user-1',
    userName: 'Max Mustermann',
    type: 'document_created',
    description: ACTIVITY_DESCRIPTIONS['document_created'],
    createdAt: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString(),
  },
  {
    id: 'activity-2',
    documentId: 'doc-1',
    userId: 'system',
    userName: 'System',
    type: 'status_changed',
    description: 'Status geaendert: Entwurf → In Pruefung',
    metadata: { oldStatus: 'draft', newStatus: 'review' },
    createdAt: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString(),
  },
  {
    id: 'activity-3',
    documentId: 'doc-1',
    userId: 'user-2',
    userName: 'Anna Schmidt',
    type: 'comment_added',
    description: ACTIVITY_DESCRIPTIONS['comment_added'],
    createdAt: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString(),
  },
  {
    id: 'activity-4',
    documentId: 'doc-1',
    userId: 'user-2',
    userName: 'Anna Schmidt',
    type: 'metadata_updated',
    description: 'hat die Rechnungsnummer korrigiert',
    metadata: { field: 'invoice_number', oldValue: 'RE-2024-001', newValue: 'RE-2024-0001' },
    createdAt: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString(),
  },
  {
    id: 'activity-5',
    documentId: 'doc-1',
    userId: 'user-3',
    userName: 'Thomas Mueller',
    type: 'document_downloaded',
    description: ACTIVITY_DESCRIPTIONS['document_downloaded'],
    createdAt: new Date(Date.now() - 1 * 24 * 60 * 60 * 1000).toISOString(),
  },
  {
    id: 'activity-6',
    documentId: 'doc-1',
    userId: 'system',
    userName: 'System',
    type: 'status_changed',
    description: 'Status geaendert: In Pruefung → Freigegeben',
    metadata: { oldStatus: 'review', newStatus: 'approved' },
    createdAt: new Date(Date.now() - 12 * 60 * 60 * 1000).toISOString(),
  },
  {
    id: 'activity-7',
    documentId: 'doc-1',
    userId: 'user-1',
    userName: 'Max Mustermann',
    type: 'tags_changed',
    description: 'hat Tags hinzugefuegt: Rechnung, Buchhaltung',
    metadata: { addedTags: ['Rechnung', 'Buchhaltung'] },
    createdAt: new Date(Date.now() - 6 * 60 * 60 * 1000).toISOString(),
  },
];

// ==================== API Functions ====================

async function fetchActivities(documentId: string): Promise<ActivitiesResponse> {
  // TODO: Replace with actual API call
  // const response = await apiClient.get<ActivitiesResponse>(`/documents/${documentId}/activity`);
  // return response.data;

  await new Promise((resolve) => setTimeout(resolve, 300));

  // Return mock data sorted by date (newest first)
  const activities = [...MOCK_ACTIVITIES]
    .filter((a) => a.documentId === documentId || documentId === 'doc-1')
    .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());

  return {
    activities,
    total: activities.length,
    hasMore: false,
  };
}

// ==================== Hook ====================

export function useActivity(documentId: string) {
  return useQuery({
    queryKey: ['activity', documentId],
    queryFn: () => fetchActivities(documentId),
    staleTime: 60000, // 1 minute
  });
}
