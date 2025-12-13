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

// Backend response (snake_case)
interface DocumentBackend {
    id: string;
    filename: string;
    original_filename: string;
    file_size: number;
    mime_type: string;
    status: 'pending' | 'processing' | 'completed' | 'failed';
    ocr_confidence?: number;
    extracted_text?: string;
    file_path?: string;
    processing_job_id?: string;
    // Quick Classification (schnelle Klassifizierung waehrend Upload)
    quick_classification_status?: 'pending' | 'processing' | 'completed' | 'failed';
    quick_classification_result?: {
        direction?: 'incoming' | 'outgoing' | 'unknown';
        confidence?: number;
        reason?: string;
        tag_assigned?: boolean;
        tag_name?: string;
    };
}

// Frontend interface (camelCase)
export interface Document {
    id: string;
    name: string;
    title?: string;
    mimeType: string;
    size: number;
    createdAt: string;
    ocrStatus: 'pending' | 'processing' | 'completed' | 'failed';
    ocrConfidence?: number;
    thumbnail?: string;
    fileUrl?: string;
    extractedText?: string;
    ocrResults?: {
        pages: Array<{
            text: string;
            confidence: number;
            boxes?: Array<BoundingBox>;
        }>;
    };
    /** Celery Task ID for OCR progress tracking */
    taskId?: string;
    /** Quick Classification Status (schnelle Klassifizierung) */
    quickClassificationStatus?: 'pending' | 'processing' | 'completed' | 'failed';
    /** Quick Classification Result */
    quickClassificationResult?: {
        direction?: 'incoming' | 'outgoing' | 'unknown';
        confidence?: number;
        reason?: string;
        tagAssigned?: boolean;
        tagName?: string;
    };
}

// Transform backend response to frontend format
function transformDocument(doc: DocumentBackend): Document {
    // DEBUG: Log raw API response for quick classification
    if (doc.quick_classification_status || doc.quick_classification_result) {
        console.log('[QC Transform] Raw API response:', {
            quick_classification_status: doc.quick_classification_status,
            quick_classification_result: doc.quick_classification_result,
        });
    }
    return {
        id: doc.id,
        name: doc.original_filename || doc.filename,
        title: doc.original_filename || doc.filename,
        mimeType: doc.mime_type,
        size: doc.file_size,
        createdAt: new Date().toISOString(),
        ocrStatus: doc.status,
        ocrConfidence: doc.ocr_confidence,
        extractedText: doc.extracted_text,
        fileUrl: `/documents/${doc.id}/preview`,
        taskId: doc.processing_job_id,
        // Quick Classification
        quickClassificationStatus: doc.quick_classification_status,
        quickClassificationResult: doc.quick_classification_result ? {
            direction: doc.quick_classification_result.direction,
            confidence: doc.quick_classification_result.confidence,
            reason: doc.quick_classification_result.reason,
            tagAssigned: doc.quick_classification_result.tag_assigned,
            tagName: doc.quick_classification_result.tag_name,
        } : undefined,
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
        const response = await apiClient.get<DocumentBackend[]>('/documents', { params: filters });
        return response.data.map(transformDocument);
    },

    getById: async (id: string) => {
        const response = await apiClient.get<DocumentBackend>(`/documents/${id}`);
        return transformDocument(response.data);
    },

    upload: async (
        file: File,
        options?: { ocrBackend?: string },
        onProgress?: (progress: number) => void
    ) => {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('ocr_backend', options?.ocrBackend || 'auto');

        const response = await apiClient.post<DocumentBackend>('/documents', formData, {
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
        return transformDocument(response.data);
    },

    delete: async (id: string) => {
        await apiClient.delete(`/documents/${id}`);
    },

    /**
     * Bestätigt oder ändert die Dokumentklassifizierung (Eingangs-/Ausgangsrechnung).
     * Setzt den entsprechenden Tag am Dokument.
     */
    confirmClassification: async (
        documentId: string,
        data: {
            invoice_direction: 'incoming' | 'outgoing';
            user_overridden: boolean;
        }
    ): Promise<{
        status: string;
        document_id: string;
        applied_tag: string;
        invoice_direction: 'incoming' | 'outgoing';
    }> => {
        const response = await apiClient.post(
            `/documents/${documentId}/confirm-classification`,
            data
        );
        return response.data;
    },

    /**
     * Holt die extrahierten Daten eines Dokuments (inkl. Klassifizierung).
     */
    getExtractedData: async (documentId: string): Promise<{
        invoice?: {
            invoice_direction?: 'incoming' | 'outgoing' | 'unknown';
            invoice_direction_confidence?: number;
            invoice_direction_reason?: string;
        };
    } | null> => {
        try {
            const response = await apiClient.get(`/extracted-data/${documentId}`);
            return response.data;
        } catch {
            // Falls keine extrahierten Daten vorhanden sind
            return null;
        }
    },
};
