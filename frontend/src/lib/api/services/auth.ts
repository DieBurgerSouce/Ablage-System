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

// Backend response structure - can be either token or 2FA required
interface LoginResponse {
    access_token?: string;
    refresh_token?: string;
    token_type?: string;
    session_warning?: string | null;
    // 2FA required response
    requires_2fa?: boolean;
    temp_token?: string;
    message?: string;
}

export interface TwoFactorRequiredResponse {
    requires_2fa: true;
    temp_token: string;
    message: string;
}

export interface TwoFactorStatus {
    enabled: boolean;
    available?: boolean;
    setup_at: string | null;
    backup_codes_remaining: number;
    has_pending_setup: boolean;
}

export interface TwoFactorSetupResponse {
    message: string;
    qr_code: string;
    secret: string;
    backup_codes: string[];
}

interface UserResponse {
    id: string;
    email: string;
    username: string;
    full_name?: string;
    is_superuser: boolean;
    is_active: boolean;
    role?: 'admin' | 'editor' | 'viewer';
}

export interface AuthResponse {
    user: User;
    token: string;
    refreshToken: string;
}

export type LoginResult = AuthResponse | TwoFactorRequiredResponse;

export const authService = {
    login: async (email: string, password: string): Promise<LoginResult> => {
        // Login to get tokens or 2FA requirement
        const loginResponse = await apiClient.post<LoginResponse>('/auth/login', { email, password });

        // Check if 2FA is required
        if (loginResponse.data.requires_2fa && loginResponse.data.temp_token) {
            return {
                requires_2fa: true,
                temp_token: loginResponse.data.temp_token,
                message: loginResponse.data.message || 'Bitte geben Sie Ihren 2FA-Code ein.',
            };
        }

        if (loginResponse.data.access_token) {
            // Phase 1.1: sessionStorage statt localStorage (XSS-Mitigation)
            sessionStorage.setItem('auth_token', loginResponse.data.access_token);
            sessionStorage.setItem('refresh_token', loginResponse.data.refresh_token || '');

            // Fetch user info with the new token
            const userResponse = await apiClient.get<UserResponse>('/auth/me', {
                headers: { Authorization: `Bearer ${loginResponse.data.access_token.trim()}` }
            });

            const user: User = {
                id: userResponse.data.id,
                email: userResponse.data.email,
                username: userResponse.data.username,
                full_name: userResponse.data.full_name,
                is_superuser: userResponse.data.is_superuser,
                is_active: userResponse.data.is_active,
                // Use role from backend if available, fallback to computed value
                role: userResponse.data.role || (userResponse.data.is_superuser ? 'admin' : 'viewer'),
            };
            sessionStorage.setItem('user', JSON.stringify(user));

            return {
                user,
                token: loginResponse.data.access_token,
                refreshToken: loginResponse.data.refresh_token || '',
            };
        }
        throw new Error('Login fehlgeschlagen');
    },

    verify2FA: async (tempToken: string, code: string): Promise<AuthResponse> => {
        const response = await apiClient.post<LoginResponse>('/auth/verify-2fa', {
            temp_token: tempToken,
            code,
        });

        if (response.data.access_token) {
            sessionStorage.setItem('auth_token', response.data.access_token);
            sessionStorage.setItem('refresh_token', response.data.refresh_token || '');

            // Fetch user info
            const userResponse = await apiClient.get<UserResponse>('/auth/me', {
                headers: { Authorization: `Bearer ${response.data.access_token.trim()}` }
            });

            const user: User = {
                id: userResponse.data.id,
                email: userResponse.data.email,
                username: userResponse.data.username,
                full_name: userResponse.data.full_name,
                is_superuser: userResponse.data.is_superuser,
                is_active: userResponse.data.is_active,
                role: userResponse.data.role || (userResponse.data.is_superuser ? 'admin' : 'viewer'),
            };
            sessionStorage.setItem('user', JSON.stringify(user));

            return {
                user,
                token: response.data.access_token,
                refreshToken: response.data.refresh_token || '',
            };
        }
        throw new Error('2FA-Verifizierung fehlgeschlagen');
    },

    // MFA (Multi-Factor Authentication) Methods - verwendet /mfa/* Endpoints
    get2FAStatus: async (): Promise<TwoFactorStatus> => {
        const response = await apiClient.get<TwoFactorStatus>('/mfa/status');
        return response.data;
    },

    setup2FA: async (): Promise<TwoFactorSetupResponse> => {
        const response = await apiClient.post<TwoFactorSetupResponse>('/mfa/setup');
        return response.data;
    },

    verify2FASetup: async (code: string): Promise<void> => {
        await apiClient.post('/mfa/verify', { code });
    },

    disable2FA: async (code: string): Promise<void> => {
        await apiClient.post('/mfa/disable', { code });
    },

    regenerateBackupCodes: async (code: string): Promise<string[]> => {
        const response = await apiClient.post<{ backup_codes: string[] }>('/mfa/regenerate', { code });
        return response.data.backup_codes;
    },

    // Validate TOTP code (used during login)
    validateTOTP: async (code: string): Promise<void> => {
        await apiClient.post('/mfa/validate', { code });
    },

    // Use backup code (alternative to TOTP)
    useBackupCode: async (code: string): Promise<void> => {
        await apiClient.post('/mfa/backup', { code });
    },

    logout: () => {
        sessionStorage.removeItem('auth_token');
        sessionStorage.removeItem('refresh_token');
        sessionStorage.removeItem('user');
        window.location.href = '/login';
    },

    refreshToken: async (): Promise<string> => {
        const refreshToken = sessionStorage.getItem('refresh_token');
        if (!refreshToken) throw new Error('No refresh token available');

        const response = await apiClient.post<LoginResponse>('/auth/refresh', { refresh_token: refreshToken });
        if (response.data.access_token) {
            sessionStorage.setItem('auth_token', response.data.access_token);
            sessionStorage.setItem('refresh_token', response.data.refresh_token);
        }
        return response.data.access_token;
    },

    getCurrentUser: (): User | null => {
        const userStr = sessionStorage.getItem('user');
        if (!userStr) return null;
        try {
            return JSON.parse(userStr);
        } catch {
            return null;
        }
    },

    isAuthenticated: (): boolean => {
        return !!sessionStorage.getItem('auth_token');
    },

    // Password Reset Methods
    requestPasswordReset: async (email: string): Promise<void> => {
        await apiClient.post('/auth/forgot-password', { email });
        // Note: Backend always returns 200 to prevent email enumeration
    },

    validateResetToken: async (token: string): Promise<boolean> => {
        try {
            const response = await apiClient.post<{ valid: boolean }>('/auth/validate-reset-token', { token });
            return response.data.valid;
        } catch {
            return false;
        }
    },

    resetPassword: async (token: string, newPassword: string): Promise<void> => {
        await apiClient.post('/auth/reset-password', {
            token,
            new_password: newPassword,
        });
    },
};

/**
 * Helper-Funktion um das Auth-Token zu holen.
 * Wird für WebSocket-Authentifizierung benötigt.
 *
 * @returns Access Token oder null wenn nicht eingeloggt
 */
export function getAuthToken(): string | null {
    return sessionStorage.getItem('auth_token');
}
