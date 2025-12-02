import { apiClient } from '../client';

export interface User {
    id: string;
    email: string;
    name: string;
    role: 'admin' | 'editor' | 'viewer';
}

export interface AuthResponse {
    user: User;
    token: string;
    refreshToken: string;
}

export const authService = {
    login: async (email: string, password: string): Promise<AuthResponse> => {
        const response = await apiClient.post<AuthResponse>('/auth/login', { email, password });
        if (response.data.token) {
            localStorage.setItem('auth_token', response.data.token);
            localStorage.setItem('refresh_token', response.data.refreshToken);
            localStorage.setItem('user', JSON.stringify(response.data.user));
        }
        return response.data;
    },

    logout: () => {
        localStorage.removeItem('auth_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('user');
        window.location.href = '/login';
    },

    refreshToken: async (): Promise<string> => {
        const refreshToken = localStorage.getItem('refresh_token');
        if (!refreshToken) throw new Error('No refresh token available');

        const response = await apiClient.post<{ token: string }>('/auth/refresh', { refreshToken });
        if (response.data.token) {
            localStorage.setItem('auth_token', response.data.token);
        }
        return response.data.token;
    },

    getCurrentUser: (): User | null => {
        const userStr = localStorage.getItem('user');
        if (!userStr) return null;
        try {
            return JSON.parse(userStr);
        } catch {
            return null;
        }
    },

    isAuthenticated: (): boolean => {
        return !!localStorage.getItem('auth_token');
    }
};
