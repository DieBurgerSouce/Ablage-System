import { apiClient } from '../client';

export interface TaskProgress {
    task_id: string;
    state: 'PENDING' | 'STARTED' | 'SUCCESS' | 'FAILURE' | 'PROGRESS';
    ready: boolean;
    progress: number;
    current?: number;
    total?: number;
    message?: string;
    result?: Record<string, unknown>;
    error?: string;
}

export const tasksService = {
    /**
     * Get the status and progress of a Celery task
     */
    getStatus: async (taskId: string): Promise<TaskProgress> => {
        const response = await apiClient.get<TaskProgress>(`/tasks/${taskId}`);
        return response.data;
    },

    /**
     * Cancel a running task
     */
    cancel: async (taskId: string): Promise<{ cancelled: boolean }> => {
        const response = await apiClient.delete<{ cancelled: boolean }>(`/tasks/${taskId}`);
        return response.data;
    },
};
