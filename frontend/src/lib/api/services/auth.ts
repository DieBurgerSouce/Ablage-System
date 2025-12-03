import { apiClient } from '../client';

export interface User {
    id: string;
    email: string;
    username: string;
    full_name?: string;
    is_superuser: boolean;
    is_active: boolean;
    role: 'admin' | 'editor' | 'viewer';
}

// Backend response structure
interface LoginResponse {
    access_token: string;
    refresh_token: string;
    token_type: string;
    session_warning?: string | null;
}

interface UserResponse {
    id: string;
    email: string;
    username: string;
    full_name?: string;
    is_superuser: boolean;
    is_active: boolean;
}

export interface AuthResponse {
    user: User;
    token: string;
    refreshToken: string;
}

export const authService = {
    login: async (email: string, password: string): Promise<AuthResponse> => {
        // Login to get tokens
        const loginResponse = await apiClient.post<LoginResponse>('/auth/login', { email, password });

        if (loginResponse.data.access_token) {
            localStorage.setItem('auth_token', loginResponse.data.access_token);
            localStorage.setItem('refresh_token', loginResponse.data.refresh_token);

            // Fetch user info with the new token
            const userResponse = await apiClient.get<UserResponse>('/auth/me', {
                headers: { Authorization: `Bearer ${loginResponse.data.access_token}` }
            });

            const user: User = {
                id: userResponse.data.id,
                email: userResponse.data.email,
                username: userResponse.data.username,
                full_name: userResponse.data.full_name,
                is_superuser: userResponse.data.is_superuser,
                is_active: userResponse.data.is_active,
                role: userResponse.data.is_superuser ? 'admin' : 'viewer',
            };
            localStorage.setItem('user', JSON.stringify(user));

            return {
                user,
                token: loginResponse.data.access_token,
                refreshToken: loginResponse.data.refresh_token,
            };
        }
        throw new Error('Login fehlgeschlagen');
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

        const response = await apiClient.post<LoginResponse>('/auth/refresh', { refresh_token: refreshToken });
        if (response.data.access_token) {
            localStorage.setItem('auth_token', response.data.access_token);
            localStorage.setItem('refresh_token', response.data.refresh_token);
        }
        return response.data.access_token;
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
