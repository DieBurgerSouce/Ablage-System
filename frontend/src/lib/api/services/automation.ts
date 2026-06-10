import { apiClient } from '../client';
import { type Node, type Edge } from '@xyflow/react';

export interface AutomationRule {
    id: string;
    name: string;
    enabled: boolean;
    nodes: Node[];
    edges: Edge[];
    createdAt: string;
    updatedAt: string;
}

// ===== Auto-Filing (F1 Vertrauens-Loop) =====

export interface FilingSuggestion {
    rule_id: string;
    rule_name: string;
    target_folder_id: string | null;
    target_category: string | null;
    confidence: number;
    model_type: string;
    auto_file: boolean;
}

export interface FilingAcceptResponse {
    document_id: string;
    filed: boolean;
    target_category: string;
    message: string;
}

export const automationService = {
    getAllRules: async () => {
        const response = await apiClient.get<AutomationRule[]>('/automation/rules');
        return response.data;
    },

    /** Ablage-Vorschläge für ein Dokument (sortiert nach Konfidenz). */
    getFilingSuggestions: async (documentId: string): Promise<FilingSuggestion[]> => {
        const response = await apiClient.get<FilingSuggestion[]>(
            `/automation/filing-suggestions/${documentId}`
        );
        return response.data;
    },

    /**
     * Bestätigt (oder korrigiert) die Ablage eines Dokuments.
     * targetCategory ist die angenommene oder vom Nutzer gewählte Kategorie.
     */
    acceptFilingSuggestion: async (
        documentId: string,
        targetCategory: string
    ): Promise<FilingAcceptResponse> => {
        const response = await apiClient.post<FilingAcceptResponse>(
            `/automation/filing-suggestions/${documentId}/accept`,
            { target_category: targetCategory }
        );
        return response.data;
    },

    getRuleById: async (id: string) => {
        const response = await apiClient.get<AutomationRule>(`/automation/rules/${id}`);
        return response.data;
    },

    createRule: async (rule: Omit<AutomationRule, 'id' | 'createdAt' | 'updatedAt'>) => {
        const response = await apiClient.post<AutomationRule>('/automation/rules', rule);
        return response.data;
    },

    updateRule: async (id: string, rule: Partial<AutomationRule>) => {
        const response = await apiClient.put<AutomationRule>(`/automation/rules/${id}`, rule);
        return response.data;
    },

    deleteRule: async (id: string) => {
        await apiClient.delete(`/automation/rules/${id}`);
    },
};
