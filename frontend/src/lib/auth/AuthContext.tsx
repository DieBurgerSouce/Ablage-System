import React, { createContext, useContext, useEffect, useState } from 'react';
import { authService, type User, type LoginResult, type AuthResponse, type TwoFactorRequiredResponse } from '@/lib/api/services/auth';

// Type guard to check if result requires 2FA
export function is2FARequired(result: LoginResult): result is TwoFactorRequiredResponse {
    return 'requires_2fa' in result && result.requires_2fa === true;
}

interface AuthContextType {
    user: User | null;
    isLoading: boolean;
    login: (email: string, password: string) => Promise<LoginResult>;
    verify2FA: (tempToken: string, code: string) => Promise<AuthResponse>;
    logout: typeof authService.logout;
    isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
    const [user, setUser] = useState<User | null>(null);
    const [isLoading, setIsLoading] = useState(true);

    useEffect(() => {
        const initAuth = async () => {
            try {
                const currentUser = authService.getCurrentUser();
                if (currentUser) {
                    setUser(currentUser);
                    // Optional: Verify token validity with backend here
                }
            } catch (error) {
                console.error('Auth initialization failed', error);
                authService.logout();
            } finally {
                setIsLoading(false);
            }
        };

        initAuth();
    }, []);

    const login = async (email: string, password: string): Promise<LoginResult> => {
        const response = await authService.login(email, password);
        // Only set user if we got a full auth response (not 2FA required)
        if (!is2FARequired(response)) {
            setUser(response.user);
        }
        return response;
    };

    const verify2FA = async (tempToken: string, code: string): Promise<AuthResponse> => {
        const response = await authService.verify2FA(tempToken, code);
        setUser(response.user);
        return response;
    };

    const logout = () => {
        authService.logout();
        setUser(null);
    };

    return (
        <AuthContext.Provider value={{
            user,
            isLoading,
            login,
            verify2FA,
            logout,
            isAuthenticated: !!user
        }}>
            {children}
        </AuthContext.Provider>
    );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
    const context = useContext(AuthContext);
    if (context === undefined) {
        throw new Error('useAuth must be used within an AuthProvider');
    }
    return context;
}
