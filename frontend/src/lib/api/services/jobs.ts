import { apiClient } from '../client';

export interface Job {
    id: string;
    type: 'ocr' | 'classification' | 'extraction';
    status: 'pending' | 'processing' | 'completed' | 'failed';
    progress: number;
    documentId: string;
    createdAt: string;
    updatedAt: string;
    error?: string;
}

export const jobsService = {
    getAll: async () => {
        const response = await apiClient.get<Job[]>('/jobs');
        return response.data;
    },

    getById: async (id: string) => {
        const response = await apiClient.get<Job>(`/jobs/${id}`);
        return response.data;
    },

    cancel: async (id: string) => {
        await apiClient.post(`/jobs/${id}/cancel`);
    },

    retry: async (id: string) => {
        await apiClient.post(`/jobs/${id}/retry`);
    },
};
