import { apiClient } from '../client';

export interface GPUMetrics {
    utilization: number;
    vramUsed: number;
    vramTotal: number;
    temperature: number;
    time: number;
}

export interface Dashboard {
    name: string;
    url: string;
    description: string;
    icon: string;
}

export interface DashboardsResponse {
    enabled: boolean;
    grafana_base?: string;
    dashboards: Record<string, Dashboard>;
    message?: string;
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

    /**
     * Hole Grafana Dashboard Links
     */
    getDashboards: async (): Promise<DashboardsResponse> => {
        const response = await apiClient.get<DashboardsResponse>('/metrics/dashboards');
        return response.data;
    },
};
