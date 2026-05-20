import { apiClient } from '../client';

/**
 * Group Types (aus Backend DocumentGroup Model)
 */
export type DocumentGroupType =
    | 'stapled'
    | 'multi_page'
    | 'transaction'
    | 'correspondence'
    | 'project'
    | 'manual';

/**
 * Backend response interface (snake_case)
 */
interface DocumentGroupBackend {
    id: string;
    name: string;
    description?: string;
    group_type: DocumentGroupType;
    total_pages: number;
    detection_confidence?: number;
    user_confirmed: boolean;
    primary_document_id?: string;
    business_entity_id?: string;
    created_at: string;
    updated_at?: string;
}

/**
 * Frontend interface (camelCase)
 */
export interface DocumentGroup {
    id: string;
    name: string;
    description?: string;
    groupType: DocumentGroupType;
    totalPages: number;
    detectionConfidence?: number;
    userConfirmed: boolean;
    primaryDocumentId?: string;
    businessEntityId?: string;
    createdAt: string;
    updatedAt?: string;
}

/**
 * Request interface für Gruppen-Erstellung
 */
export interface DocumentGroupCreate {
    name: string;
    description?: string;
    group_type: DocumentGroupType;
    document_ids: string[];
    primary_document_id?: string;
    business_entity_id?: string;
}

/**
 * Request interface für Dokument hinzufügen
 */
export interface AddDocumentToGroup {
    document_id: string;
    page_number?: number;
}

/**
 * Transform backend response to frontend format
 */
function transformGroup(group: DocumentGroupBackend): DocumentGroup {
    return {
        id: group.id,
        name: group.name,
        description: group.description,
        groupType: group.group_type,
        totalPages: group.total_pages,
        detectionConfidence: group.detection_confidence,
        userConfirmed: group.user_confirmed,
        primaryDocumentId: group.primary_document_id,
        businessEntityId: group.business_entity_id,
        createdAt: group.created_at,
        updatedAt: group.updated_at,
    };
}

/**
 * Groups API Service für DocumentGroup Management
 */
export const groupsService = {
    /**
     * Erstellt eine neue Dokumentgruppe
     */
    create: async (data: DocumentGroupCreate): Promise<DocumentGroup> => {
        const response = await apiClient.post<DocumentGroupBackend>('/groups', data);
        return transformGroup(response.data);
    },

    /**
     * Holt eine Gruppe nach ID
     */
    getById: async (groupId: string): Promise<DocumentGroup> => {
        const response = await apiClient.get<DocumentGroupBackend>(`/groups/${groupId}`);
        return transformGroup(response.data);
    },

    /**
     * Listet alle Gruppen auf (mit optionalen Filtern)
     */
    getAll: async (params?: {
        group_type?: DocumentGroupType;
        business_entity_id?: string;
        limit?: number;
        offset?: number;
    }): Promise<DocumentGroup[]> => {
        const response = await apiClient.get<DocumentGroupBackend[]>('/groups', { params });
        return response.data.map(transformGroup);
    },

    /**
     * Fügt ein Dokument zu einer bestehenden Gruppe hinzu
     */
    addDocument: async (groupId: string, documentId: string, pageNumber?: number): Promise<DocumentGroup> => {
        const response = await apiClient.post<DocumentGroupBackend>(
            `/groups/${groupId}/documents`,
            {
                document_id: documentId,
                page_number: pageNumber,
            }
        );
        return transformGroup(response.data);
    },

    /**
     * Entfernt ein Dokument aus einer Gruppe
     */
    removeDocument: async (groupId: string, documentId: string): Promise<void> => {
        await apiClient.delete(`/groups/${groupId}/documents/${documentId}`);
    },

    /**
     * Löscht eine Gruppe (Dokumente werden nicht gelöscht, nur entknüpft)
     */
    delete: async (groupId: string): Promise<void> => {
        await apiClient.delete(`/groups/${groupId}`);
    },

    /**
     * Aktualisiert Gruppen-Metadaten (Name, Beschreibung)
     */
    update: async (groupId: string, data: {
        name?: string;
        description?: string;
    }): Promise<DocumentGroup> => {
        const response = await apiClient.patch<DocumentGroupBackend>(`/groups/${groupId}`, data);
        return transformGroup(response.data);
    },

    /**
     * Holt die nächste laufende Nummer für einen Entity-Namen
     * z.B. "Alpac" -> 3 (wenn schon Alpac_001 und Alpac_002 existieren)
     */
    getNextNumber: async (entityName: string): Promise<number> => {
        try {
            const response = await apiClient.get<{ next_number: number }>(
                '/groups/next-number',
                { params: { entity: entityName } }
            );
            return response.data.next_number;
        } catch {
            // Falls Endpoint nicht existiert, starte bei 1
            return 1;
        }
    },

    /**
     * Bestätigt eine automatisch erkannte Gruppierung
     */
    confirm: async (groupId: string): Promise<DocumentGroup> => {
        const response = await apiClient.post<DocumentGroupBackend>(`/groups/${groupId}/confirm`);
        return transformGroup(response.data);
    },

    /**
     * Führt mehrere Gruppen zusammen
     */
    merge: async (targetId: string, sourceIds: string[]): Promise<DocumentGroup> => {
        const response = await apiClient.post<DocumentGroupBackend>('/groups/merge', {
            target_id: targetId,
            source_ids: sourceIds,
        });
        return transformGroup(response.data);
    },
};
