import { apiClient } from '../client';

export interface User {
    id: string;
    email: string;
    username: string;
    full_name?: string | null;
    is_active: boolean;
    is_superuser: boolean;
    tier: string;
    role: 'superuser' | 'admin' | 'user';
    status: 'active' | 'inactive' | 'deactivated';
    last_login?: string | null;
    created_at: string;
    // Convenience getter for display name
    name: string;
}

// Response type from backend (paginated)
interface UserListResponse {
    users: User[];
    total: number;
    page: number;
    per_page: number;
    total_pages: number;
}

// ==================== System Dashboard Types ====================

export interface GPUStatusAdmin {
    available: boolean;
    gpu_name: string | null;
    total_gb: number;
    free_gb: number;
    allocated_gb: number;
    memory_used_gb: number;
    memory_total_gb: number;
    utilization_percent: number;
    temperature_celsius: number | null;
    memory_usage_percent: number;
    current_allocations: string[];
    recommendations: string[];
}

export interface QueueStatus {
    pending: number;
    queued: number;
    processing: number;
    completed_today: number;
    failed_today: number;
    cancelled_today: number;
    avg_wait_seconds: number;
    avg_processing_seconds: number;
    by_priority: Record<string, number>;
    by_backend: Record<string, number>;
}

export interface BackendHealthStatus {
    name: string;
    status: 'healthy' | 'degraded' | 'unhealthy' | 'unknown';
    response_time_ms: number | null;
    last_check: string;
    details: Record<string, unknown>;
}

export interface SystemHealthStatus {
    overall_status: 'healthy' | 'degraded' | 'unhealthy';
    postgres: BackendHealthStatus;
    redis: BackendHealthStatus;
    minio: BackendHealthStatus;
    celery: BackendHealthStatus;
    gpu: BackendHealthStatus;
    last_updated: string;
}

export interface ProcessingStats {
    documents_processed_today: number;
    documents_processed_hour: number;
    success_rate: number;
    avg_processing_time_ms: number;
    total_documents: number;
    total_pages_processed: number;
    by_backend: Record<string, { count: number; avg_time_ms: number; success_rate: number }>;
    by_document_type: Record<string, number>;
    hourly_trend: Array<{ hour: string; count: number; success_rate: number }>;
}

export interface SystemDashboard {
    gpu: GPUStatusAdmin;
    queue: QueueStatus;
    health: SystemHealthStatus;
    processing: ProcessingStats;
    timestamp: string;
}

// ==================== Skonto Warning Types ====================

export interface SkontoWarningItem {
    id: string;
    sender_company: string;
    invoice_number?: string;
    gross_amount: number;
    discount_percent: number;
    discount_amount: number;
    discount_due_date: string;
    days_until: number;
}

export interface SkontoWarningsResponse {
    items: SkontoWarningItem[];
    total: number;
    total_savings: number;
}

export const adminService = {
    getUsers: async (): Promise<User[]> => {
        const response = await apiClient.get<UserListResponse>('/admin/users');
        // Backend returns paginated response with users in 'users' property
        // Map to add 'name' field for display (using full_name or username)
        const users = response.data.users || [];
        return users.map(user => ({
            ...user,
            name: user.full_name || user.username,
        }));
    },

    createUser: async (user: Omit<User, 'id' | 'lastLogin'>) => {
        const response = await apiClient.post<User>('/admin/users', user);
        return response.data;
    },

    updateUser: async (id: string, user: Partial<User>) => {
        const response = await apiClient.put<User>(`/admin/users/${id}`, user);
        return response.data;
    },

    deleteUser: async (id: string) => {
        await apiClient.delete(`/admin/users/${id}`);
    },

    // ==================== System Dashboard ====================

    /**
     * Holt das vollständige System-Dashboard
     */
    getSystemDashboard: async (): Promise<SystemDashboard> => {
        const response = await apiClient.get<SystemDashboard>('/admin/system/dashboard');
        return response.data;
    },

    /**
     * Holt den GPU-Status
     */
    getGPUStatus: async (): Promise<GPUStatusAdmin> => {
        const response = await apiClient.get<GPUStatusAdmin>('/admin/system/gpu');
        return response.data;
    },

    /**
     * Holt den Queue-Status
     */
    getQueueStatus: async (): Promise<QueueStatus> => {
        const response = await apiClient.get<QueueStatus>('/admin/system/queue');
        return response.data;
    },

    /**
     * Holt den Gesundheitsstatus
     */
    getHealthStatus: async (): Promise<SystemHealthStatus> => {
        const response = await apiClient.get<SystemHealthStatus>('/admin/system/health');
        return response.data;
    },

    /**
     * Holt Verarbeitungsstatistiken
     */
    getProcessingStats: async (days: number = 7): Promise<ProcessingStats> => {
        const response = await apiClient.get<ProcessingStats>(`/admin/system/stats?days=${days}`);
        return response.data;
    },

    /**
     * Leert den GPU-Cache
     */
    clearGPUCache: async (): Promise<{ message: string; detail: string }> => {
        const response = await apiClient.post<{ message: string; detail: string }>('/admin/system/gpu/clear-cache');
        return response.data;
    },

    /**
     * Holt Rechnungen mit ablaufendem Skonto (nächste 3 Tage)
     */
    getSkontoWarnings: async (): Promise<SkontoWarningsResponse> => {
        try {
            const response = await apiClient.get<{
                items: Array<{
                    id: string;
                    sender_company: string;
                    invoice_number?: string;
                    gross_amount: number;
                    discount_percent: number;
                    discount_due_date: string;
                    filename?: string;
                }>;
                total: number;
            }>('/extracted_data/invoices', {
                params: {
                    skonto_expiring_soon: true,
                    per_page: 10,
                },
            });

            // Berechne Einsparungen und Tage - mit korrekter Timezone-Behandlung
            // Verwende startOfDay um Zeitzonenprobleme zu vermeiden
            const today = new Date();
            today.setHours(0, 0, 0, 0); // Start des Tages für konsistente Berechnung

            const items: SkontoWarningItem[] = response.data.items.map((item) => {
                // Parse ISO-Datum und setze auf Tagesbeginn
                const dueDate = new Date(item.discount_due_date);
                dueDate.setHours(0, 0, 0, 0);

                // Differenz in ganzen Tagen
                const diffMs = dueDate.getTime() - today.getTime();
                const daysUntil = Math.round(diffMs / (1000 * 60 * 60 * 24));
                const discountAmount = item.gross_amount * (item.discount_percent / 100);

                return {
                    id: item.id,
                    sender_company: item.sender_company || 'Unbekannt',
                    invoice_number: item.invoice_number,
                    gross_amount: item.gross_amount,
                    discount_percent: item.discount_percent,
                    discount_amount: discountAmount,
                    discount_due_date: item.discount_due_date,
                    days_until: daysUntil,
                };
            });

            const totalSavings = items.reduce((sum, item) => sum + item.discount_amount, 0);

            return {
                items,
                total: response.data.total,
                total_savings: totalSavings,
            };
        } catch (error) {
            // Error-Logging für Debugging und Monitoring
            console.error('[admin.ts] getSkontoWarnings failed:', error);

            // Bei Fehler leere Response zurückgeben (graceful degradation)
            return {
                items: [],
                total: 0,
                total_savings: 0,
            };
        }
    },
};
