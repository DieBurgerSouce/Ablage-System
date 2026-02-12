import { apiClient } from '../client';

// ============================================================================
// Existing Types
// ============================================================================

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

// ============================================================================
// System Health Types (from /health/detailed)
// ============================================================================

export interface KomponentenStatus {
    gesund: boolean;
    nachricht: string | null;
    latenz_ms: number | null;
    details: Record<string, unknown> | null;
}

export interface DetailedHealthResponse {
    status: 'gesund' | 'beeinträchtigt' | 'kritisch';
    zeitstempel: string;
    version: string;
    komponenten: Record<string, KomponentenStatus>;
    zusammenfassung: string;
}

// ============================================================================
// Predictive Health Types (from /health/predictions/*)
// ============================================================================

export interface PredictionResponse {
    metric: string;
    current_value: number;
    predicted_value: number;
    threshold: number;
    eta_minutes: number | null;
    trend_per_minute: number;
    severity: string;
    recommendation: string;
    confidence: number;
    prediction_time: string;
}

export interface DegradationAlertResponse {
    backend: string;
    metric: string;
    current_value: number;
    threshold: number;
    trend_per_day: number;
    days_to_threshold: number | null;
    severity: string;
    recommendation: string;
    confidence: number;
}

export interface PredictiveAlertResponse {
    id: string;
    alert_type: string;
    severity: string;
    title: string;
    message: string;
    recommendation: string;
    eta_minutes: number | null;
    confidence: number;
    source: string;
    created_at: string;
    acknowledged: boolean;
}

// ============================================================================
// Service
// ============================================================================

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

    /**
     * Detaillierte Gesundheitsprüfung aller Komponenten
     */
    getDetailedHealth: async (): Promise<DetailedHealthResponse> => {
        const response = await apiClient.get<DetailedHealthResponse>('/health/detailed');
        return response.data;
    },

    /**
     * Proaktive Alerts basierend auf Vorhersagen
     */
    getPredictiveAlerts: async (): Promise<PredictiveAlertResponse[]> => {
        const response = await apiClient.get<PredictiveAlertResponse[]>('/health/predictions/alerts');
        return response.data;
    },

    /**
     * OCR Qualitäts-Degradation Alerts
     */
    getOCRDegradation: async (): Promise<DegradationAlertResponse[]> => {
        const response = await apiClient.get<DegradationAlertResponse[]>('/health/predictions/ocr/degradation');
        return response.data;
    },

    /**
     * Disk Space Exhaustion Vorhersage
     */
    getDiskPredictions: async (): Promise<PredictionResponse | null> => {
        const response = await apiClient.get<PredictionResponse | null>('/health/predictions/disk');
        return response.data;
    },

    /**
     * GPU VRAM Overflow Vorhersage
     */
    getGPUPredictions: async (): Promise<PredictionResponse | null> => {
        const response = await apiClient.get<PredictionResponse | null>('/health/predictions/gpu');
        return response.data;
    },

    /**
     * Queue Overflow Vorhersagen
     */
    getQueuePredictions: async (): Promise<PredictionResponse[]> => {
        const response = await apiClient.get<PredictionResponse[]>('/health/predictions/queues');
        return response.data;
    },
};
