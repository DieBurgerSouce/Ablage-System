import { apiClient } from '../client';

export interface BoundingBox {
    id: string;
    x: number;
    y: number;
    width: number;
    height: number;
    confidence: number;
    text?: string;
}

export interface Document {
    id: string;
    name: string;
    title?: string; // Added for compatibility
    mimeType: string;
    size: number;
    createdAt: string;
    ocrStatus: 'pending' | 'processing' | 'completed' | 'failed';
    ocrConfidence?: number;
    thumbnail?: string;
    fileUrl?: string; // Added for viewer
    ocrResults?: {
        pages: Array<{
            text: string;
            confidence: number;
            boxes?: Array<BoundingBox>;
        }>;
    };
}

export interface DocumentFilter {
    type?: string;
    ocrStatus?: string;
    dateRange?: string;
    query?: string;
    sort?: 'date_asc' | 'date_desc' | 'name_asc' | 'name_desc';
    limit?: number;
}

export const documentsService = {
    getAll: async (filters?: DocumentFilter) => {
        const response = await apiClient.get<Document[]>('/documents', { params: filters });
        return response.data;
    },

    getById: async (id: string) => {
        const response = await apiClient.get<Document>(`/documents/${id}`);
        return response.data;
    },

    upload: async (file: File, onProgress?: (progress: number) => void) => {
        const formData = new FormData();
        formData.append('file', file);

        const response = await apiClient.post<Document>('/documents', formData, {
            headers: {
                'Content-Type': 'multipart/form-data',
            },
            onUploadProgress: (progressEvent) => {
                if (progressEvent.total && onProgress) {
                    const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
                    onProgress(percentCompleted);
                }
            },
        });
        return response.data;
    },

    delete: async (id: string) => {
        await apiClient.delete(`/documents/${id}`);
    },
};
