import { apiClient } from '../client';
import type { DocumentRelationship } from '@/features/relationships/types';

export const relationshipsService = {
    getAll: async () => {
        const response = await apiClient.get<DocumentRelationship[]>('/relationships');
        return response.data;
    },

    getByDocumentId: async (documentId: string) => {
        const response = await apiClient.get<DocumentRelationship[]>(`/documents/${documentId}/relationships`);
        return response.data;
    },

    create: async (relationship: Omit<DocumentRelationship, 'id' | 'createdAt'>) => {
        const response = await apiClient.post<DocumentRelationship>('/relationships', relationship);
        return response.data;
    },

    delete: async (id: string) => {
        await apiClient.delete(`/relationships/${id}`);
    }
};
