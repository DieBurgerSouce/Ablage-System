import { apiClient } from '../client';

export interface GPUMetrics {
    utilization: number;
    vramUsed: number;
    vramTotal: number;
    temperature: number;
    time: number;
}

export const monitoringService = {
    getGPUMetrics: async () => {
        const response = await apiClient.get<GPUMetrics>('/monitoring/gpu');
        return response.data;
    },

    getSystemHealth: async () => {
        const response = await apiClient.get('/monitoring/health');
        return response.data;
    },
};
