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

export const automationService = {
    getAllRules: async () => {
        const response = await apiClient.get<AutomationRule[]>('/automation/rules');
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
