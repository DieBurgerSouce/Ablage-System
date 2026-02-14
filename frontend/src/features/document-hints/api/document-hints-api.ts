import { apiClient } from '@/lib/api/client';

// ==================== Types ====================

export type HintCategory =
    | 'missing_document'
    | 'skonto_deadline'
    | 'entity_risk'
    | 'payment_overdue'
    | 'ocr_quality'
    | 'duplicate_suspect'
    | 'compliance'
    | 'action_required';

export type HintSeverity = 'info' | 'warning' | 'critical';

export type HintActionType =
    | 'navigate'
    | 'download'
    | 'link_entity'
    | 'review_ocr'
    | 'mark_paid'
    | 'contact_entity'
    | 'external_link';

export interface DocumentHintSchema {
    category: HintCategory;
    severity: HintSeverity;
    title: string;
    message: string;
    action_label?: string;
    action_type?: HintActionType;
    action_data?: Record<string, unknown>;
    confidence: number;
    expires_at?: string;
}

export interface DocumentHintsResponse {
    hints: DocumentHintSchema[];
    total: number;
}

export interface BatchHintsResponse {
    hints: Record<string, DocumentHintSchema[]>;
    total: number;
}

export interface HintSummarySchema {
    by_category: Record<HintCategory, number>;
    by_severity: Record<HintSeverity, number>;
    total: number;
    critical_count: number;
}

// Backend response types (snake_case)
interface DocumentHintBackend {
    category: string;
    severity: string;
    title: string;
    message: string;
    action_label?: string;
    action_type?: string;
    action_data?: Record<string, unknown>;
    confidence: number;
    expires_at?: string;
}

interface DocumentHintsResponseBackend {
    hints: DocumentHintBackend[];
    total: number;
}

interface BatchHintsResponseBackend {
    hints: Record<string, DocumentHintBackend[]>;
    total: number;
}

interface HintSummaryBackend {
    by_category: Record<string, number>;
    by_severity: Record<string, number>;
    total: number;
    critical_count: number;
}

// ==================== Transformers ====================

function transformDocumentHint(hint: DocumentHintBackend): DocumentHintSchema {
    return {
        category: hint.category as HintCategory,
        severity: hint.severity as HintSeverity,
        title: hint.title,
        message: hint.message,
        action_label: hint.action_label,
        action_type: hint.action_type as HintActionType | undefined,
        action_data: hint.action_data,
        confidence: hint.confidence,
        expires_at: hint.expires_at,
    };
}

function transformDocumentHintsResponse(response: DocumentHintsResponseBackend): DocumentHintsResponse {
    return {
        hints: response.hints.map(transformDocumentHint),
        total: response.total,
    };
}

function transformBatchHintsResponse(response: BatchHintsResponseBackend): BatchHintsResponse {
    const transformedHints: Record<string, DocumentHintSchema[]> = {};

    for (const [docId, hints] of Object.entries(response.hints)) {
        transformedHints[docId] = hints.map(transformDocumentHint);
    }

    return {
        hints: transformedHints,
        total: response.total,
    };
}

function transformHintSummary(summary: HintSummaryBackend): HintSummarySchema {
    return {
        by_category: summary.by_category as Record<HintCategory, number>,
        by_severity: summary.by_severity as Record<HintSeverity, number>,
        total: summary.total,
        critical_count: summary.critical_count,
    };
}

// ==================== API Functions ====================

/**
 * Document Hints API Service
 */
export const documentHintsApi = {
    /**
     * Ruft Hinweise für ein einzelnes Dokument ab.
     */
    getDocumentHints: async (documentId: string): Promise<DocumentHintsResponse> => {
        const response = await apiClient.get<DocumentHintsResponseBackend>(
            `/documents/${documentId}/hints`
        );

        return transformDocumentHintsResponse(response.data);
    },

    /**
     * Ruft Hinweise für mehrere Dokumente ab (Batch-Operation).
     */
    getBatchDocumentHints: async (documentIds: string[]): Promise<BatchHintsResponse> => {
        const response = await apiClient.post<BatchHintsResponseBackend>(
            '/documents/hints/batch',
            {
                document_ids: documentIds,
            }
        );

        return transformBatchHintsResponse(response.data);
    },

    /**
     * Ruft die unternehmensweite Hinweis-Zusammenfassung ab.
     */
    getHintsSummary: async (): Promise<HintSummarySchema> => {
        const response = await apiClient.get<HintSummaryBackend>(
            '/documents/hints/summary'
        );

        return transformHintSummary(response.data);
    },
};

/**
 * Query Keys für React Query
 */
export const documentHintsQueryKeys = {
    all: ['document-hints'] as const,
    single: (documentId: string) => ['document-hints', documentId] as const,
    batch: (documentIds: string[]) => ['document-hints', 'batch', documentIds] as const,
    summary: () => ['document-hints', 'summary'] as const,
};
