/**
 * AI Actions API Service
 *
 * API Client für role-basierte AI-Aktionen.
 * Endpoints: /api/v1/rag/ai/*
 */

import { apiClient } from '../client';

// ============================================================================
// ENUMS - Basierend auf Backend Schemas (app/api/schemas/rag.py)
// ============================================================================

export enum AIActionType {
    // Read-Only Actions (Viewer+)
    SEARCH_DOCUMENTS = 'search_documents',
    ANALYZE_ENTITY = 'analyze_entity',
    GENERATE_REPORT = 'generate_report',
    EXPLAIN_DOCUMENT = 'explain_document',

    // Supervised Actions (Editor+)
    CATEGORIZE_DOCUMENT = 'categorize_document',
    TAG_DOCUMENT = 'tag_document',
    LINK_ENTITY = 'link_entity',
    CREATE_REMINDER = 'create_reminder',

    // Autonomous Actions (Admin only)
    APPROVE_VALIDATION = 'approve_validation',
    TRIGGER_OCR = 'trigger_ocr',
    SEND_NOTIFICATION = 'send_notification',
    BULK_CATEGORIZE = 'bulk_categorize',
}

export enum AIActionAutonomyLevel {
    VIEWER = 'viewer',     // Read-Only
    EDITOR = 'editor',     // Supervised (Vorschlag + Bestätigung)
    ADMIN = 'admin',       // Autonomous (selbstständig)
}

export enum AIActionStatus {
    PENDING = 'pending',
    SUGGESTED = 'suggested',     // Wartet auf User-Bestätigung
    CONFIRMED = 'confirmed',     // User hat bestätigt
    EXECUTING = 'executing',
    COMPLETED = 'completed',
    REJECTED = 'rejected',       // User hat abgelehnt
    FAILED = 'failed',
}

// ============================================================================
// TYPES
// ============================================================================

export interface AIActionParameter {
    name: string;
    value: unknown;
    label: string;
    editable: boolean;
}

export interface AIActionRequest {
    action_type: AIActionType;
    context_type?: string;
    context_id?: string;
    parameters: Record<string, unknown>;
    auto_execute?: boolean;
}

export interface AIActionSuggestion {
    action_id: string;
    action_type: AIActionType;
    title: string;
    description: string;
    parameters: AIActionParameter[];
    confidence: number;
    requires_confirmation: boolean;
    estimated_impact: string;
}

export interface AIActionConfirmRequest {
    action_id: string;
    confirmed: boolean;
    modified_parameters?: Record<string, unknown>;
}

export interface AIActionResult {
    action_id: string;
    action_type: AIActionType;
    status: AIActionStatus;
    message: string;
    details?: Record<string, unknown>;
    affected_items: string[];
    execution_time_ms: number;
    suggestion?: AIActionSuggestion;
}

export interface AIActionListResponse {
    available_actions: AIActionInfo[];
    autonomy_level: AIActionAutonomyLevel;
    pending_suggestions: number;
}

export interface AIActionInfo {
    action_type: AIActionType;
    name: string;
    description: string;
    required_level: AIActionAutonomyLevel;
    is_available: boolean;
    requires_confirmation: boolean;
}

export interface AIContextInfo {
    page_type: string;
    document_id?: string;
    entity_id?: string;
    suggestions: string[];
    available_actions: AIActionType[];
}

// ============================================================================
// ACTION METADATA (German labels and descriptions)
// ============================================================================

export const ACTION_METADATA: Record<AIActionType, {
    name: string;
    description: string;
    icon: string;
    requiredLevel: AIActionAutonomyLevel;
}> = {
    // Read-Only Actions (Viewer+)
    [AIActionType.SEARCH_DOCUMENTS]: {
        name: 'Dokumente suchen',
        description: 'Durchsucht alle Dokumente nach relevanten Inhalten',
        icon: 'search',
        requiredLevel: AIActionAutonomyLevel.VIEWER,
    },
    [AIActionType.ANALYZE_ENTITY]: {
        name: 'Entity analysieren',
        description: 'Analysiert einen Geschäftspartner mit allen Dokumenten',
        icon: 'user-search',
        requiredLevel: AIActionAutonomyLevel.VIEWER,
    },
    [AIActionType.GENERATE_REPORT]: {
        name: 'Bericht erstellen',
        description: 'Generiert einen Report basierend auf den Daten',
        icon: 'file-text',
        requiredLevel: AIActionAutonomyLevel.VIEWER,
    },
    [AIActionType.EXPLAIN_DOCUMENT]: {
        name: 'Dokument erklären',
        description: 'Erklärt den Inhalt und Kontext eines Dokuments',
        icon: 'book-open',
        requiredLevel: AIActionAutonomyLevel.VIEWER,
    },

    // Supervised Actions (Editor+)
    [AIActionType.CATEGORIZE_DOCUMENT]: {
        name: 'Dokument kategorisieren',
        description: 'Ordnet ein Dokument einer Kategorie zu',
        icon: 'folder-tree',
        requiredLevel: AIActionAutonomyLevel.EDITOR,
    },
    [AIActionType.TAG_DOCUMENT]: {
        name: 'Dokument taggen',
        description: 'Fügt Tags zu einem Dokument hinzu',
        icon: 'tag',
        requiredLevel: AIActionAutonomyLevel.EDITOR,
    },
    [AIActionType.LINK_ENTITY]: {
        name: 'Entity verknüpfen',
        description: 'Verknüpft ein Dokument mit einem Geschäftspartner',
        icon: 'link',
        requiredLevel: AIActionAutonomyLevel.EDITOR,
    },
    [AIActionType.CREATE_REMINDER]: {
        name: 'Erinnerung erstellen',
        description: 'Erstellt eine Erinnerung für eine Aufgabe',
        icon: 'bell',
        requiredLevel: AIActionAutonomyLevel.EDITOR,
    },

    // Autonomous Actions (Admin only)
    [AIActionType.APPROVE_VALIDATION]: {
        name: 'Validierung genehmigen',
        description: 'Genehmigt Dokumente in der Validierungs-Queue',
        icon: 'check-circle',
        requiredLevel: AIActionAutonomyLevel.ADMIN,
    },
    [AIActionType.TRIGGER_OCR]: {
        name: 'OCR starten',
        description: 'Startet die OCR-Verarbeitung für Dokumente',
        icon: 'scan',
        requiredLevel: AIActionAutonomyLevel.ADMIN,
    },
    [AIActionType.SEND_NOTIFICATION]: {
        name: 'Benachrichtigung senden',
        description: 'Sendet eine Benachrichtigung an User oder Teams',
        icon: 'mail',
        requiredLevel: AIActionAutonomyLevel.ADMIN,
    },
    [AIActionType.BULK_CATEGORIZE]: {
        name: 'Bulk-Kategorisierung',
        description: 'Kategorisiert mehrere Dokumente auf einmal',
        icon: 'layers',
        requiredLevel: AIActionAutonomyLevel.ADMIN,
    },
};

// ============================================================================
// API SERVICE
// ============================================================================

export const aiActionsApi = {
    /**
     * Listet verfügbare Aktionen basierend auf User-Rolle
     */
    getAvailableActions: async (contextType?: string): Promise<AIActionListResponse> => {
        const response = await apiClient.get<AIActionListResponse>('/rag/ai/actions', {
            params: contextType ? { context_type: contextType } : undefined,
        });
        return response.data;
    },

    /**
     * Führt eine AI-Aktion aus
     *
     * Für Editor-Level: Gibt Suggestion zurück wenn requires_confirmation
     * Für Admin-Level mit auto_execute: Führt direkt aus
     */
    executeAction: async (request: AIActionRequest): Promise<AIActionResult> => {
        const response = await apiClient.post<AIActionResult>('/rag/ai/actions/execute', request);
        return response.data;
    },

    /**
     * Bestätigt oder lehnt eine vorgeschlagene Aktion ab
     */
    confirmAction: async (request: AIActionConfirmRequest): Promise<AIActionResult> => {
        const response = await apiClient.post<AIActionResult>('/rag/ai/actions/confirm', request);
        return response.data;
    },

    /**
     * Holt Kontext-Informationen für die aktuelle Seite
     */
    getContextInfo: async (
        pageType: string,
        documentId?: string,
        entityId?: string
    ): Promise<AIContextInfo> => {
        const params: Record<string, string> = { page_type: pageType };
        if (documentId) params.document_id = documentId;
        if (entityId) params.entity_id = entityId;

        const response = await apiClient.get<AIContextInfo>('/rag/ai/context', { params });
        return response.data;
    },
};

// Default export for convenience
export default aiActionsApi;
